"""
Semantic cache with cosine similarity matching and document-based invalidation.
Prevents stale answers after document updates (critical for patient safety).
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

import numpy as np


@dataclass
class CacheEntry:
    query: str
    query_vector: np.ndarray
    answer: str
    confidence: float
    document_ids: Set[str]  # Documents used to generate this answer
    created_at: float = field(default_factory=time.time)
    ttl_seconds: int = 3600
    hit_count: int = 0

    def is_expired(self) -> bool:
        return time.time() - self.created_at > self.ttl_seconds


class SemanticCache:
    """
    Caches query responses using semantic similarity.
    Invalidates entries when source documents are updated.
    """

    def __init__(
        self,
        similarity_threshold: float = 0.90,
        ttl_seconds: int = 3600,
        max_entries: int = 10000,
        enabled: bool = True,
    ):
        self.similarity_threshold = similarity_threshold
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self.enabled = enabled
        self._store: List[CacheEntry] = []
        self._embedding_fn = None

    def set_embedding_fn(self, fn) -> None:
        """Set the embedding function (from EmbeddingEngine)."""
        self._embedding_fn = fn

    def get(self, query: str) -> Optional[str]:
        """Get cached answer if a similar query exists."""
        if not self.enabled or not self._embedding_fn:
            return None

        self._evict_expired()

        if not self._store:
            return None

        query_vec = self._embedding_fn([query])[0]
        best_score, best_entry = self._find_best(query_vec)

        if best_score >= self.similarity_threshold and best_entry:
            best_entry.hit_count += 1
            return best_entry.answer

        return None

    def put(
        self,
        query: str,
        answer: str,
        confidence: float,
        document_ids: Optional[Set[str]] = None,
    ) -> None:
        """Cache a query-answer pair."""
        if not self.enabled or not self._embedding_fn:
            return

        # Evict if at capacity (LRU: remove oldest)
        if len(self._store) >= self.max_entries:
            self._store.pop(0)

        query_vec = self._embedding_fn([query])[0]
        entry = CacheEntry(
            query=query,
            query_vector=query_vec,
            answer=answer,
            confidence=confidence,
            document_ids=document_ids or set(),
            ttl_seconds=self.ttl_seconds,
        )
        self._store.append(entry)

    def invalidate_by_document(self, doc_id: str) -> int:
        """
        Invalidate all cache entries that used a specific document.
        Called when a document is updated to prevent stale answers.
        """
        before = len(self._store)
        self._store = [e for e in self._store if doc_id not in e.document_ids]
        invalidated = before - len(self._store)
        return invalidated

    def clear(self) -> None:
        self._store.clear()

    def size(self) -> int:
        return len(self._store)

    def stats(self) -> Dict:
        total_hits = sum(e.hit_count for e in self._store)
        return {
            "size": len(self._store),
            "total_hits": total_hits,
            "threshold": self.similarity_threshold,
            "ttl_seconds": self.ttl_seconds,
        }

    def _find_best(self, query_vec: np.ndarray) -> Tuple[float, Optional[CacheEntry]]:
        if not self._store:
            return 0.0, None
        vectors = np.array([e.query_vector for e in self._store], dtype=np.float32)
        scores = np.dot(vectors, query_vec)
        best_idx = int(np.argmax(scores))
        return float(scores[best_idx]), self._store[best_idx]

    def _evict_expired(self) -> None:
        self._store = [e for e in self._store if not e.is_expired()]
