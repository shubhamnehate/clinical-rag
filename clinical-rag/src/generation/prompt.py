"""
Prompt construction with context assembly, token budgeting, and PII guard (Layer 2).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from ..ingestion.embedding import SearchResult
from ..ingestion.pii_detection import PIIDetector


@dataclass
class BuiltPrompt:
    system_prompt: str
    user_message: str
    context_chunks: List[str]
    token_estimate: int
    pii_guard_triggered: bool = False
    pii_types_found: List[str] = field(default_factory=list)


_SYSTEM_PROMPT = """You are a clinical decision support assistant. Your role is to answer questions about patient medical records accurately and concisely.

CRITICAL RULES:
1. Only answer based on the provided context. Do not use external knowledge.
2. If the answer is not in the context, say "The information is not available in the provided records."
3. Never reveal or reconstruct patient identifiers, names, or PII.
4. Always cite which document/section the answer comes from when possible.
5. Use professional medical language but explain clearly.
6. Flag if information seems inconsistent or incomplete.

RESPONSE FORMAT:
- Lead with the direct answer
- Follow with supporting evidence from context
- Note confidence level if uncertain
- Cite source sections"""


class PromptBuilder:
    """
    Assembles context from retrieval results into a prompt.
    Applies Layer 2 PII guard before sending to LLM.
    """

    def __init__(
        self,
        pii_detector: Optional[PIIDetector] = None,
        max_context_tokens: int = 8000,
        reserved_response_tokens: int = 2000,
    ):
        self.pii_detector = pii_detector or PIIDetector()
        self.max_context_tokens = max_context_tokens
        self.reserved_response_tokens = reserved_response_tokens

    def build(
        self,
        query: str,
        retrieved_results: List[SearchResult],
        patient_id: Optional[str] = None,
        query_type: Optional[str] = None,
    ) -> BuiltPrompt:
        """Build prompt from query and retrieved context chunks."""
        pii_guard_triggered = False
        pii_types: List[str] = []

        # Assemble context with token budget management
        context_parts, token_count = self._assemble_context(retrieved_results)

        # Layer 2: PII guard - scan assembled context before sending to LLM
        safe_context_parts = []
        for i, (text, source) in enumerate(context_parts):
            detected, types = self.pii_detector.scan_output(text)
            if detected:
                pii_guard_triggered = True
                pii_types.extend(types)
                # Re-pseudonymize any residual PII
                result = self.pii_detector.process(f"context_{i}", text)
                safe_context_parts.append((result.pseudonymized_content, source))
            else:
                safe_context_parts.append((text, source))

        # Build context string
        context_str = self._format_context(safe_context_parts)

        # Build user message
        user_message = f"""PATIENT CONTEXT:
{context_str}

QUESTION: {query}

Please answer based solely on the context above."""

        if patient_id:
            user_message = f"Patient ID: {patient_id}\n\n" + user_message

        return BuiltPrompt(
            system_prompt=_SYSTEM_PROMPT,
            user_message=user_message,
            context_chunks=[text for text, _ in safe_context_parts],
            token_estimate=token_count + len(query) // 4,
            pii_guard_triggered=pii_guard_triggered,
            pii_types_found=list(set(pii_types)),
        )

    def _assemble_context(
        self, results: List[SearchResult]
    ) -> Tuple[List[Tuple[str, str]], int]:
        """Assemble context chunks respecting token budget."""
        parts = []
        total_tokens = 0
        budget = self.max_context_tokens - self.reserved_response_tokens

        for result in results:
            chunk_tokens = result.chunk.token_count
            if total_tokens + chunk_tokens > budget:
                break
            source = f"[{result.chunk.document_type or 'document'} | {result.chunk.section or 'general'} | score: {result.score:.2f}]"
            parts.append((result.chunk.text, source))
            total_tokens += chunk_tokens

        return parts, total_tokens

    def _format_context(self, parts: List[Tuple[str, str]]) -> str:
        if not parts:
            return "No relevant context found."
        lines = []
        for i, (text, source) in enumerate(parts, 1):
            lines.append(f"--- Context {i} {source} ---\n{text}")
        return "\n\n".join(lines)
