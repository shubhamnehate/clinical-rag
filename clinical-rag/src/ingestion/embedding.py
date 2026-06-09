"""
Embedding generation and in-memory vector store.
Supports sentence-transformers for dense embeddings.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .chunking import DocumentChunk


@dataclass
class EmbeddedChunk:
    chunk: DocumentChunk
    vector: np.ndarray


@dataclass
class SearchResult:
    chunk: DocumentChunk
    score: float
    rank: int = 0


class EmbeddingEngine:
    """
    Generates dense embeddings using sentence-transformers.
    Falls back to TF-IDF-like hashing if model unavailable.
    Stores embeddings in memory (swap for Pinecone/Milvus in production).
    """

    def __init__(
        self,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        dimension: int = 384,
        normalize: bool = True,
    ):
        self.model_name = model_name
        self.dimension = dimension
        self.normalize = normalize
        self._model = None
        self._store: List[EmbeddedChunk] = []
        self._load_model()

    def _load_model(self):
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)
            self.dimension = self._model.get_sentence_embedding_dimension()
        except ImportError:
            self._model = None  # Will use fallback

    def encode(self, texts: List[str]) -> np.ndarray:
        """Encode a list of texts into vectors."""
        if self._model is not None:
            vectors = self._model.encode(texts, normalize_embeddings=self.normalize)
            return np.array(vectors, dtype=np.float32)
        else:
            return self._fallback_encode(texts)

    def _fallback_encode(self, texts: List[str]) -> np.ndarray:
        """Simple TF-based fallback when sentence-transformers unavailable."""
        dim = self.dimension
        result = []
        for text in texts:
            vec = np.zeros(dim, dtype=np.float32)
            words = text.lower().split()
            for word in words:
                # Simple hash-based feature
                idx = abs(hash(word)) % dim
                vec[idx] += 1.0
            # L2 normalize
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            result.append(vec)
        return np.array(result, dtype=np.float32)

    def add_chunks(self, chunks: List[DocumentChunk]) -> None:
        """Embed and store chunks."""
        if not chunks:
            return
        texts = [c.text for c in chunks]
        vectors = self.encode(texts)
        for chunk, vector in zip(chunks, vectors):
            self._store.append(EmbeddedChunk(chunk=chunk, vector=vector))

    def search(
        self,
        query: str,
        top_k: int = 10,
        patient_id: Optional[str] = None,
        document_type: Optional[str] = None,
        min_score: float = 0.0,
    ) -> List[SearchResult]:
        """Search for most similar chunks using cosine similarity."""
        if not self._store:
            return []

        query_vec = self.encode([query])[0]

        # Filter by patient_id if specified
        candidates = self._store
        if patient_id:
            candidates = [e for e in candidates if e.chunk.patient_id == patient_id]
        if document_type:
            candidates = [e for e in candidates if e.chunk.document_type == document_type]

        if not candidates:
            return []

        # Batch cosine similarity
        vectors = np.array([e.vector for e in candidates], dtype=np.float32)
        scores = np.dot(vectors, query_vec)

        # Get top_k
        top_indices = np.argsort(scores)[::-1][:top_k]
        results = []
        for rank, idx in enumerate(top_indices):
            score = float(scores[idx])
            if score >= min_score:
                results.append(SearchResult(
                    chunk=candidates[idx].chunk,
                    score=score,
                    rank=rank,
                ))
        return results

    def remove_document(self, doc_id: str) -> int:
        """Remove all chunks for a document (for versioning/updates)."""
        before = len(self._store)
        self._store = [e for e in self._store if e.chunk.parent_doc_id != doc_id]
        return before - len(self._store)

    def get_store_size(self) -> int:
        return len(self._store)

    def clear(self) -> None:
        self._store.clear()
