"""
Main Clinical RAG Pipeline Orchestrator.

Ties together all components:
  Ingestion → Query Intelligence → Retrieval → Generation → Post-Processing

Critical flows:
  1. Structured queries bypass vector search
  2. Feedback loop closes from post-processor back to retrieval
  3. 3-layer PII protection runs at every stage
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from .cache.semantic_cache import SemanticCache
from .generation.llm import LLMClient, LLMResponse
from .generation.prompt import PromptBuilder
from .ingestion.chunking import ChunkingEngine, DocumentChunk
from .ingestion.embedding import EmbeddingEngine
from .ingestion.loaders import DocumentLoader, LoadedDocument
from .ingestion.pii_detection import PIIDetector
from .observability.audit import AuditTrail
from .observability.logging_config import get_logger
from .observability.metrics import MetricsCollector, QueryMetrics
from .post_processing.confidence import ConfidenceScorer
from .post_processing.feedback_loop import FeedbackLoopController
from .post_processing.validation import OutputValidator
from .query.classifier import QueryClassifier
from .query.expander import QueryExpander
from .query.router import QueryRouter
from .retrieval.dense import DenseRetriever
from .retrieval.hybrid import HybridRetriever
from .retrieval.reranker import CrossEncoderReranker
from .retrieval.sparse import SparseRetriever
from .structured.fhir_parser import FHIRParser
from .structured.hl7_parser import HL7Parser
from .structured.query_builder import StructuredQueryBuilder

logger = get_logger(__name__)


@dataclass
class QueryResponse:
    query_id: str
    query: str
    answer: str
    confidence: float
    confidence_level: str
    cache_hit: bool
    retry_count: int
    retrieval_count: int
    route: str
    pii_guard_triggered: bool
    pii_output_detected: bool
    latency_ms: float
    warnings: List[str] = field(default_factory=list)
    structured_results: Optional[Dict] = None


@dataclass
class IngestionResult:
    document_id: str
    chunks_created: int
    pii_detected: bool
    pii_entities_count: int
    version: int
    success: bool
    error: Optional[str] = None


class ClinicalRAGPipeline:
    """
    Complete Clinical RAG Pipeline.
    Orchestrates all components from ingestion to generation.
    """

    def __init__(
        self,
        pii_salt: str = "default_salt_change_me",
        anthropic_api_key: Optional[str] = None,
        embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
        llm_model: str = "claude-sonnet-4-5-20250929",
        cache_enabled: bool = True,
        mock_llm: bool = False,
        audit_log_path: Optional[str] = None,
        reranker_enabled: bool = True,
    ):
        # --- PII Detection (shared across all layers) ---
        self.pii_detector = PIIDetector(salt=pii_salt)

        # --- Ingestion ---
        self.loader = DocumentLoader()
        self.chunker = ChunkingEngine()
        self.embedding_engine = EmbeddingEngine(model_name=embedding_model)

        # --- Query Intelligence ---
        self.classifier = QueryClassifier()
        self.router = QueryRouter()
        self.expander = QueryExpander()

        # --- Retrieval ---
        self.dense_retriever = DenseRetriever(self.embedding_engine)
        self.sparse_retriever = SparseRetriever()
        self.hybrid_retriever = HybridRetriever(self.dense_retriever, self.sparse_retriever)
        self.reranker = CrossEncoderReranker(enabled=reranker_enabled)

        # --- Generation ---
        self.prompt_builder = PromptBuilder(pii_detector=self.pii_detector)
        self.llm = LLMClient(
            api_key=anthropic_api_key,
            model=llm_model,
            mock=mock_llm,
        )

        # --- Post-Processing ---
        self.confidence_scorer = ConfidenceScorer()
        self.output_validator = OutputValidator(pii_detector=self.pii_detector)
        self.feedback_controller = FeedbackLoopController()

        # --- Structured Data ---
        self.fhir_parser = FHIRParser()
        self.hl7_parser = HL7Parser()
        self.structured_query_builder = StructuredQueryBuilder()

        # --- Cache ---
        self.cache = SemanticCache(enabled=cache_enabled)
        self.cache.set_embedding_fn(self.embedding_engine.encode)

        # --- Observability ---
        self.audit = AuditTrail(log_path=audit_log_path)
        self.metrics = MetricsCollector()

        # Document version tracking
        self._document_versions: Dict[str, int] = {}

        logger.info("Clinical RAG Pipeline initialized")

    # =========================================================================
    # INGESTION
    # =========================================================================

    def ingest_text(
        self,
        document_id: str,
        text: str,
        content_type: str = "clinical_note",
        patient_id: Optional[str] = None,
        document_date: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> IngestionResult:
        """Ingest a text document into the pipeline."""
        return self._ingest_document(
            document_id=document_id,
            text=text,
            content_type=content_type,
            patient_id=patient_id,
            document_date=document_date,
            metadata=metadata or {},
        )

    def ingest_file(self, file_path: str, patient_id: Optional[str] = None) -> IngestionResult:
        """Load and ingest a file."""
        doc = self.loader.load(file_path)
        if doc.load_error:
            return IngestionResult(
                document_id=doc.document_id,
                chunks_created=0,
                pii_detected=False,
                pii_entities_count=0,
                version=0,
                success=False,
                error=doc.load_error,
            )
        return self._ingest_document(
            document_id=doc.document_id,
            text=doc.text_content,
            content_type=doc.content_type,
            patient_id=patient_id or doc.structured_data.get("patient_id"),
            structured_data=doc.structured_data,
        )

    def ingest_fhir(self, resource: Dict, patient_id: Optional[str] = None) -> IngestionResult:
        """Ingest a FHIR resource into the structured data store."""
        parsed = self.fhir_parser.parse(resource)
        self.structured_query_builder.add_fhir_resource(parsed)
        # Also create a text representation for hybrid retrieval
        text = self.loader._fhir_to_text(resource)
        return self._ingest_document(
            document_id=f"fhir_{resource.get('resourceType', 'unknown')}_{resource.get('id', uuid.uuid4().hex[:8])}",
            text=text,
            content_type="fhir_resource",
            patient_id=patient_id or parsed.patient_id,
        )

    def _ingest_document(
        self,
        document_id: str,
        text: str,
        content_type: str,
        patient_id: Optional[str] = None,
        document_date: Optional[str] = None,
        structured_data: Optional[Dict] = None,
        metadata: Optional[Dict] = None,
    ) -> IngestionResult:
        try:
            # Determine version
            version = self._document_versions.get(document_id, 0) + 1
            self._document_versions[document_id] = version

            # If re-ingesting: remove old chunks
            if version > 1:
                removed = self.embedding_engine.remove_document(document_id)
                self.sparse_retriever.remove_document(document_id)
                # Invalidate cache entries that used this document
                invalidated = self.cache.invalidate_by_document(document_id)
                logger.info(
                    f"Versioning: doc={document_id} v{version}, "
                    f"removed={removed} chunks, cache_invalidated={invalidated}"
                )

            # Layer 1: PII detection and pseudonymization
            pii_result = self.pii_detector.process(document_id, text)
            if pii_result.pii_detected:
                self.audit.log_pii_event(
                    document_id=document_id,
                    pii_types=[e.entity_type for e in pii_result.pii_entities],
                    layer=1,
                )

            safe_text = pii_result.pseudonymized_content

            # Chunk the document
            chunks = self.chunker.chunk(
                doc_id=document_id,
                text=safe_text,
                patient_id=patient_id,
                document_date=document_date,
                document_type=content_type,
                version=version,
            )

            if not chunks:
                return IngestionResult(
                    document_id=document_id,
                    chunks_created=0,
                    pii_detected=pii_result.pii_detected,
                    pii_entities_count=len(pii_result.pii_entities),
                    version=version,
                    success=True,
                )

            # Embed and store in vector index
            self.embedding_engine.add_chunks(chunks)

            # Add to sparse (BM25) index
            self.sparse_retriever.index(chunks)

            self.audit.log_document_access(
                user_id=None,
                patient_id=patient_id,
                document_id=document_id,
                action="ingest",
            )

            logger.info(
                f"Ingested doc={document_id} type={content_type} "
                f"chunks={len(chunks)} pii={pii_result.pii_detected} v={version}"
            )

            return IngestionResult(
                document_id=document_id,
                chunks_created=len(chunks),
                pii_detected=pii_result.pii_detected,
                pii_entities_count=len(pii_result.pii_entities),
                version=version,
                success=True,
            )

        except Exception as e:
            logger.error(f"Ingestion failed for {document_id}: {e}")
            return IngestionResult(
                document_id=document_id,
                chunks_created=0,
                pii_detected=False,
                pii_entities_count=0,
                version=self._document_versions.get(document_id, 0),
                success=False,
                error=str(e),
            )

    # =========================================================================
    # QUERY
    # =========================================================================

    def query(
        self,
        query: str,
        patient_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> QueryResponse:
        """
        Execute a clinical query through the full RAG pipeline.

        Flow:
          1. Check cache
          2. Classify query type
          3. Expand query
          4. Route to appropriate retrieval strategy
          5. Retrieve relevant chunks
          6. Build prompt (Layer 2 PII guard)
          7. Generate answer
          8. Score confidence
          9. Post-process (Layer 3 PII scan)
         10. Feedback loop if low confidence
         11. Cache result
         12. Return response
        """
        start_time = time.time()
        query_id = uuid.uuid4().hex[:16]
        warnings: List[str] = []

        self.audit.log_query(
            user_id=user_id,
            patient_id=patient_id,
            query_id=query_id,
            query=query,
        )

        # Step 1: Cache check
        cached = self.cache.get(query)
        if cached:
            latency = (time.time() - start_time) * 1000
            self.metrics.record_query(QueryMetrics(
                query_id=query_id, latency_ms=latency, confidence=1.0,
                cache_hit=True, retry_count=0, retrieval_count=0,
            ))
            return QueryResponse(
                query_id=query_id, query=query, answer=cached,
                confidence=1.0, confidence_level="high",
                cache_hit=True, retry_count=0, retrieval_count=0,
                route="cache", pii_guard_triggered=False,
                pii_output_detected=False, latency_ms=latency,
            )

        # Step 2: Classify query
        classification = self.classifier.classify(query)
        logger.debug(f"Classified query as {classification.query_type} (conf={classification.confidence:.2f})")

        # Step 3: Expand query
        expanded = self.expander.expand(query)

        # Step 4: Route
        route_decision = self.router.route(classification)
        route = route_decision.route

        # Step 5: Structured query path (bypass vector search)
        if route == "structured_query":
            struct_result = self.structured_query_builder.query(
                natural_language_query=query,
                patient_id=patient_id,
            )
            answer = struct_result.answer_text
            latency = (time.time() - start_time) * 1000
            return QueryResponse(
                query_id=query_id, query=query, answer=answer,
                confidence=0.9, confidence_level="high",
                cache_hit=False, retry_count=0, retrieval_count=struct_result.total_count,
                route="structured_query", pii_guard_triggered=False,
                pii_output_detected=False, latency_ms=latency,
                structured_results={"results": struct_result.results[:5]},
            )

        # Step 5: Vector retrieval with feedback loop
        params = route_decision.parameters
        k = params.get("k", 5)
        use_dense = params.get("use_dense", True)
        use_sparse = params.get("use_sparse", True)
        do_rerank = params.get("rerank", True)

        best_answer = ""
        best_confidence = None
        best_results = []
        attempt = 0
        pii_guard_triggered = False
        pii_output_detected = False

        current_query = expanded.expanded_query_string

        while True:
            # Retrieve
            retrieved = self.hybrid_retriever.retrieve(
                query=current_query,
                top_k=k,
                patient_id=patient_id,
                use_dense=use_dense,
                use_sparse=use_sparse,
            )

            # Log document accesses for audit
            seen_docs: Set[str] = set()
            for r in retrieved:
                if r.chunk.parent_doc_id not in seen_docs:
                    seen_docs.add(r.chunk.parent_doc_id)
                    self.audit.log_document_access(
                        user_id=user_id,
                        patient_id=patient_id,
                        document_id=r.chunk.parent_doc_id,
                        action="query_retrieval",
                    )

            # Rerank
            if do_rerank and retrieved:
                retrieved = self.reranker.rerank(current_query, retrieved)

            # Build prompt (Layer 2 PII guard)
            built_prompt = self.prompt_builder.build(
                query=query,
                retrieved_results=retrieved,
                patient_id=patient_id,
                query_type=classification.query_type.value,
            )
            if built_prompt.pii_guard_triggered:
                pii_guard_triggered = True
                warnings.append(f"Layer 2 PII guard activated: {built_prompt.pii_types_found}")

            # Generate
            llm_response = self.llm.generate(
                system_prompt=built_prompt.system_prompt,
                user_message=built_prompt.user_message,
            )

            # Layer 3: Output PII scan + validation
            validation = self.output_validator.validate(llm_response.answer)
            if validation.pii_detected:
                pii_output_detected = True
                self.audit.log_pii_event(
                    document_id=f"output_{query_id}",
                    pii_types=validation.pii_types_found,
                    layer=3,
                    blocked=validation.blocked,
                )
                warnings.append(f"Layer 3 PII detected in output: {validation.pii_types_found}")
                if validation.blocked:
                    warnings.append("Response blocked due to PII")

            validated_answer = validation.answer

            # Score confidence
            confidence = self.confidence_scorer.score(
                answer=validated_answer,
                retrieved_results=retrieved,
                query=query,
            )

            best_results = retrieved
            best_answer = validated_answer
            best_confidence = confidence

            # Feedback loop decision
            feedback = self.feedback_controller.decide(
                confidence=confidence,
                query=query,
                attempt=attempt,
                expanded_query=expanded.expanded_query_string,
            )

            if not feedback.should_retry:
                break

            # Retry: update parameters
            logger.info(f"Feedback loop retry {attempt + 1}: {feedback.reason}")
            if feedback.action == "expand_query":
                current_query = feedback.expanded_query or current_query
            elif feedback.action == "increase_k":
                k = feedback.new_k or k * 2
            attempt += 1

        # Add confidence warning if needed
        final_answer = self.feedback_controller.add_confidence_warning(best_answer, best_confidence)

        # Cache result (only if valid and no PII issues)
        if best_confidence.score >= 0.5 and not pii_output_detected:
            doc_ids = {r.chunk.parent_doc_id for r in best_results}
            self.cache.put(
                query=query,
                answer=final_answer,
                confidence=best_confidence.score,
                document_ids=doc_ids,
            )

        latency = (time.time() - start_time) * 1000

        self.metrics.record_query(QueryMetrics(
            query_id=query_id,
            latency_ms=latency,
            confidence=best_confidence.score,
            cache_hit=False,
            retry_count=attempt,
            retrieval_count=len(best_results),
            pii_detected_in_output=pii_output_detected,
        ))

        logger.info(
            f"Query done: id={query_id} conf={best_confidence.score:.2f} "
            f"latency={latency:.0f}ms retries={attempt}"
        )

        return QueryResponse(
            query_id=query_id,
            query=query,
            answer=final_answer,
            confidence=best_confidence.score,
            confidence_level=best_confidence.level,
            cache_hit=False,
            retry_count=attempt,
            retrieval_count=len(best_results),
            route=route,
            pii_guard_triggered=pii_guard_triggered,
            pii_output_detected=pii_output_detected,
            latency_ms=latency,
            warnings=warnings,
        )

    def get_metrics(self) -> Dict:
        """Return current system metrics."""
        summary = self.metrics.get_summary()
        summary["cache_stats"] = self.cache.stats()
        summary["store_size"] = self.embedding_engine.get_store_size()
        return summary
