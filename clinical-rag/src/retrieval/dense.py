"""Dense retrieval using the embedding engine's vector store."""
from __future__ import annotations

from typing import List, Optional

from ..ingestion.embedding import EmbeddingEngine, SearchResult


class DenseRetriever:
    """Wraps the embedding engine for dense vector retrieval with patient-level filtering."""

    def __init__(self, embedding_engine: EmbeddingEngine):
        self.engine = embedding_engine

    def retrieve(
        self,
        query: str,
        top_k: int = 10,
        patient_id: Optional[str] = None,
        document_type: Optional[str] = None,
        min_score: float = 0.0,
    ) -> List[SearchResult]:
        return self.engine.search(
            query=query,
            top_k=top_k,
            patient_id=patient_id,
            document_type=document_type,
            min_score=min_score,
        )
