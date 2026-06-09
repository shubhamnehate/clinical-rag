"""
Sparse retrieval using BM25.
Builds an index over stored chunks for keyword-based matching.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from ..ingestion.chunking import DocumentChunk
from ..ingestion.embedding import SearchResult


class SparseRetriever:
    """
    BM25-based sparse retrieval.
    Uses rank-bm25 library if available, falls back to simple TF-based scoring.
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self._chunks: List[DocumentChunk] = []
        self._bm25 = None

    def index(self, chunks: List[DocumentChunk]) -> None:
        """Add chunks to the BM25 index."""
        self._chunks.extend(chunks)
        self._rebuild_index()

    def _rebuild_index(self):
        if not self._chunks:
            return
        tokenized = [self._tokenize(c.text) for c in self._chunks]
        try:
            from rank_bm25 import BM25Okapi
            self._bm25 = BM25Okapi(tokenized, k1=self.k1, b=self.b)
        except ImportError:
            self._bm25 = None  # Will use fallback

    def retrieve(
        self,
        query: str,
        top_k: int = 10,
        patient_id: Optional[str] = None,
    ) -> List[SearchResult]:
        if not self._chunks:
            return []

        query_tokens = self._tokenize(query)

        if self._bm25 is not None:
            scores = self._bm25.get_scores(query_tokens)
        else:
            scores = self._fallback_scores(query_tokens)

        # Filter by patient_id if specified
        candidates = list(enumerate(self._chunks))
        if patient_id:
            candidates = [(i, c) for i, c in candidates if c.patient_id == patient_id]

        # Sort by score
        scored = [(scores[i], c) for i, c in candidates]
        scored.sort(key=lambda x: x[0], reverse=True)

        results = []
        for rank, (score, chunk) in enumerate(scored[:top_k]):
            if score > 0:
                results.append(SearchResult(chunk=chunk, score=float(score), rank=rank))
        return results

    def _tokenize(self, text: str) -> List[str]:
        """Simple whitespace + lowercase tokenizer."""
        import re
        return re.findall(r"\b\w+\b", text.lower())

    def _fallback_scores(self, query_tokens: List[str]) -> List[float]:
        """Simple TF-based scoring fallback."""
        scores = []
        query_set = set(query_tokens)
        for chunk in self._chunks:
            chunk_tokens = self._tokenize(chunk.text)
            chunk_set = set(chunk_tokens)
            overlap = len(query_set & chunk_set)
            tf_score = overlap / max(len(chunk_tokens), 1)
            scores.append(tf_score)
        return scores

    def remove_document(self, doc_id: str) -> None:
        self._chunks = [c for c in self._chunks if c.parent_doc_id != doc_id]
        self._rebuild_index()

    def clear(self) -> None:
        self._chunks.clear()
        self._bm25 = None
