"""
Feedback loop controller: triggers re-retrieval on low confidence.
Closes the loop from post-processor back to retrieval pipeline.
CRITICAL design requirement: feedback must close back to retrieval.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional

from ..ingestion.embedding import SearchResult
from .confidence import ConfidenceResult


@dataclass
class FeedbackAction:
    should_retry: bool
    action: str  # "return", "expand_query", "increase_k", "clarify"
    expanded_query: Optional[str] = None
    new_k: Optional[int] = None
    attempt: int = 1
    reason: str = ""


class FeedbackLoopController:
    """
    Controls re-retrieval based on confidence score.

    Logic:
    - High confidence (>0.7): return answer
    - Medium confidence (0.5-0.7): retry with query expansion (attempt 1)
    - Low confidence (<0.5): retry with more chunks (attempt 2)
    - After max_retries: return best answer with low-confidence warning
    """

    def __init__(
        self,
        max_retries: int = 2,
        high_threshold: float = 0.7,
        low_threshold: float = 0.5,
    ):
        self.max_retries = max_retries
        self.high_threshold = high_threshold
        self.low_threshold = low_threshold

    def decide(
        self,
        confidence: ConfidenceResult,
        query: str,
        attempt: int,
        expanded_query: Optional[str] = None,
    ) -> FeedbackAction:
        """Decide whether to retry or return the current answer."""

        # Max retries reached
        if attempt >= self.max_retries:
            return FeedbackAction(
                should_retry=False,
                action="return",
                attempt=attempt,
                reason=f"Max retries ({self.max_retries}) reached",
            )

        # High confidence: return immediately
        if confidence.score >= self.high_threshold:
            return FeedbackAction(
                should_retry=False,
                action="return",
                attempt=attempt,
                reason=f"High confidence: {confidence.score:.2f}",
            )

        # Medium confidence on first attempt: retry with expanded query
        if confidence.score >= self.low_threshold and attempt == 0:
            return FeedbackAction(
                should_retry=True,
                action="expand_query",
                expanded_query=expanded_query or self._make_broader_query(query),
                attempt=attempt + 1,
                reason=f"Medium confidence: {confidence.score:.2f}, expanding query",
            )

        # Low confidence: retry with more chunks
        if confidence.score < self.low_threshold and attempt < self.max_retries:
            return FeedbackAction(
                should_retry=True,
                action="increase_k",
                new_k=20,
                attempt=attempt + 1,
                reason=f"Low confidence: {confidence.score:.2f}, increasing k",
            )

        return FeedbackAction(
            should_retry=False,
            action="return",
            attempt=attempt,
            reason="No improvement strategy available",
        )

    def _make_broader_query(self, query: str) -> str:
        """Create a broader version of the query for retry."""
        # Remove specific constraints to broaden search
        broader = query.replace(" exact ", " ").replace(" only ", " ")
        # Add "related" to broaden semantic search
        if len(query.split()) < 10:
            broader = query + " related information"
        return broader

    def add_confidence_warning(self, answer: str, confidence: ConfidenceResult) -> str:
        """Append confidence warning to low-confidence answers."""
        if confidence.score < self.low_threshold:
            return (
                answer
                + f"\n\n[Note: Low confidence ({confidence.score:.0%}). "
                "The retrieved records may not fully address this query. "
                "Please verify with the original clinical records.]"
            )
        elif confidence.score < self.high_threshold:
            return (
                answer
                + f"\n\n[Note: Moderate confidence ({confidence.score:.0%}). "
                "Consider reviewing source records for complete information.]"
            )
        return answer
