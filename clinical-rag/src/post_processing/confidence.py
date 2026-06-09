"""
Confidence scoring for generated answers.
Combines retrieval quality, answer coherence, and citation presence.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

from ..ingestion.embedding import SearchResult


@dataclass
class ConfidenceResult:
    score: float  # 0.0 - 1.0
    level: str    # high (>0.7), medium (0.5-0.7), low (<0.5)
    factors: dict


class ConfidenceScorer:
    """
    Scores confidence based on:
    1. Average retrieval relevance score
    2. Number of retrieved chunks
    3. Answer coherence signals (length, references no-info)
    4. Presence of "not available" fallback phrases
    """

    def __init__(
        self,
        high_threshold: float = 0.7,
        low_threshold: float = 0.5,
    ):
        self.high_threshold = high_threshold
        self.low_threshold = low_threshold

    def score(
        self,
        answer: str,
        retrieved_results: List[SearchResult],
        query: str,
    ) -> ConfidenceResult:
        factors = {}

        # Factor 1: Retrieval quality (avg score of top results)
        if retrieved_results:
            avg_score = sum(r.score for r in retrieved_results[:5]) / min(5, len(retrieved_results))
            factors["retrieval_avg_score"] = round(avg_score, 3)
        else:
            avg_score = 0.0
            factors["retrieval_avg_score"] = 0.0

        # Factor 2: Number of supporting chunks
        n_chunks = len(retrieved_results)
        chunk_factor = min(1.0, n_chunks / 3.0)  # 3+ chunks = full credit
        factors["supporting_chunks"] = n_chunks

        # Factor 3: Answer quality signals
        answer_lower = answer.lower()
        not_available_phrases = [
            "not available", "not found", "no information",
            "cannot find", "not in the provided", "not mentioned",
            "llm error",
        ]
        has_fallback = any(p in answer_lower for p in not_available_phrases)
        factors["has_fallback_phrase"] = has_fallback

        # Factor 4: Answer length (very short answers may be low confidence)
        answer_len = len(answer.split())
        length_factor = min(1.0, answer_len / 20.0)  # 20+ words = full credit
        factors["answer_word_count"] = answer_len

        # Compute composite score
        if has_fallback:
            composite = 0.3
        else:
            # Weighted combination
            composite = (
                0.4 * min(1.0, avg_score)
                + 0.3 * chunk_factor
                + 0.3 * length_factor
            )

        composite = round(max(0.0, min(1.0, composite)), 3)
        factors["composite_score"] = composite

        if composite >= self.high_threshold:
            level = "high"
        elif composite >= self.low_threshold:
            level = "medium"
        else:
            level = "low"

        return ConfidenceResult(score=composite, level=level, factors=factors)
