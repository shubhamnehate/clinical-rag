"""
Cross-encoder reranker for improved result ranking.
Uses cross-encoder/ms-marco-MiniLM-L-6-v2 or falls back to score pass-through.
"""
from __future__ import annotations

from typing import List

from ..ingestion.embedding import SearchResult


class CrossEncoderReranker:
    """
    Cross-encoder reranker. Better precision than bi-encoder but slower.
    Falls back gracefully if cross-encoder not available.
    """

    def __init__(
        self,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
        top_k: int = 5,
        enabled: bool = True,
    ):
        self.model_name = model_name
        self.top_k = top_k
        self.enabled = enabled
        self._model = None
        self._load_model()

    def _load_model(self):
        if not self.enabled:
            return
        try:
            from sentence_transformers import CrossEncoder
            self._model = CrossEncoder(self.model_name)
        except (ImportError, Exception):
            self._model = None

    def rerank(self, query: str, results: List[SearchResult]) -> List[SearchResult]:
        """Rerank results using cross-encoder scores."""
        if not results:
            return results

        if self._model is None or not self.enabled:
            # Pass-through: just return top_k by existing score
            return sorted(results, key=lambda r: r.score, reverse=True)[: self.top_k]

        # Build query-document pairs
        pairs = [(query, r.chunk.text) for r in results]

        try:
            scores = self._model.predict(pairs)
        except Exception:
            return results[: self.top_k]

        # Re-sort by cross-encoder score
        reranked = sorted(
            zip(scores, results),
            key=lambda x: x[0],
            reverse=True,
        )

        output = []
        for rank, (score, result) in enumerate(reranked[: self.top_k]):
            output.append(SearchResult(
                chunk=result.chunk,
                score=float(score),
                rank=rank,
            ))
        return output
