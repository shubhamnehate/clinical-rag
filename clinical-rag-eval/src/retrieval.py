"""
Retrieval Module — Clinical RAG Prototype
==========================================
Implements a three-stage pipeline:

  Stage 1 — DUAL RETRIEVAL (Dense + Sparse in parallel)
    • Dense:  sentence-transformer embeddings → cosine similarity
              Captures semantic meaning: "cardiac event" ≡ "MI"
    • Sparse: BM25 keyword matching
              Captures exact clinical terms: "troponin", "furosemide 80mg"
    Why both? Dense alone misses exact drug names/doses; sparse alone misses
    paraphrases. Clinical queries mix both: "what BP meds is she on" needs
    semantic understanding AND exact term matching.

  Stage 2 — RECIPROCAL RANK FUSION (RRF)
    • Merges dense and sparse ranked lists without score normalisation
    • RRF(d, s) = α/(k+rank_dense) + (1-α)/(k+rank_sparse)
    • k=60 dampens impact of very high ranks; α=0.65 (dense-biased)
    Why RRF over score combination? Scores from cosine similarity and BM25
    are on incomparable scales. RRF only uses rank ordinal, robust to scaling.

  Stage 3 — CROSS-ENCODER RE-RANKING (optional)
    • If available: cross-encoder/ms-marco-MiniLM-L-6-v2 scores each
      (query, chunk) pair jointly — much stronger than bi-encoder
    • Falls back to score pass-through if model unavailable
    Why reranking? Bi-encoder embeddings are fast but approximate.
    Cross-encoder reads query+document together, catches clinical nuance:
    "what medications caused the rash?" vs "what medications is he on"
    both retrieve medication chunks but reranker separates them.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from .chunking import Chunk


@dataclass
class RetrievalResult:
    chunk: Chunk
    dense_score: float = 0.0
    sparse_score: float = 0.0
    rrf_score: float = 0.0
    rerank_score: float = 0.0
    final_rank: int = 0

    @property
    def best_score(self) -> float:
        return self.rerank_score if self.rerank_score else self.rrf_score


# ── Embedding engine ─────────────────────────────────────────────────────────

class EmbeddingEngine:
    """Thin wrapper around sentence-transformers with hash fallback."""

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self.model_name = model_name
        self._model = None
        self._dim = 384
        self._load()

    def _load(self):
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)
            self._dim = self._model.get_sentence_embedding_dimension()
            print(f"  [EmbeddingEngine] Loaded '{self.model_name}' (dim={self._dim})")
        except ImportError:
            print("  [EmbeddingEngine] sentence-transformers not found — using hash fallback")

    def encode(self, texts: List[str]) -> np.ndarray:
        if self._model:
            vecs = self._model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
            return np.array(vecs, dtype=np.float32)
        return self._hash_encode(texts)

    def _hash_encode(self, texts: List[str]) -> np.ndarray:
        """Deterministic hash-based fallback (captures vocabulary overlap)."""
        out = []
        for text in texts:
            vec = np.zeros(self._dim, dtype=np.float32)
            for w in text.lower().split():
                vec[abs(hash(w)) % self._dim] += 1.0
            norm = np.linalg.norm(vec)
            out.append(vec / norm if norm > 0 else vec)
        return np.array(out, dtype=np.float32)


# ── Sparse retriever (BM25) ──────────────────────────────────────────────────

class BM25Index:
    """BM25Okapi with vocabulary-based fallback."""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self._chunks: List[Chunk] = []
        self._bm25 = None

    def build(self, chunks: List[Chunk]) -> None:
        self._chunks = chunks
        corpus = [self._tok(c.text) for c in chunks]
        try:
            from rank_bm25 import BM25Okapi
            self._bm25 = BM25Okapi(corpus, k1=self.k1, b=self.b)
            print(f"  [BM25Index] Built over {len(chunks)} chunks with rank-bm25")
        except ImportError:
            self._bm25 = None
            print("  [BM25Index] rank-bm25 not found — using TF fallback")

    def query(self, q: str, top_k: int) -> List[Tuple[Chunk, float]]:
        if not self._chunks:
            return []
        tokens = self._tok(q)
        if self._bm25:
            scores = self._bm25.get_scores(tokens)
        else:
            scores = self._tf_scores(tokens)
        idx = np.argsort(scores)[::-1][:top_k]
        return [(self._chunks[i], float(scores[i])) for i in idx if scores[i] > 0]

    def _tok(self, text: str) -> List[str]:
        import re
        return re.findall(r"\b\w+\b", text.lower())

    def _tf_scores(self, qtokens: List[str]) -> List[float]:
        qset = set(qtokens)
        return [
            len(qset & set(self._tok(c.text))) / max(len(self._tok(c.text)), 1)
            for c in self._chunks
        ]


# ── Hybrid retriever ─────────────────────────────────────────────────────────

class HybridRetriever:
    """Dense + Sparse + RRF Fusion + optional Cross-Encoder Re-ranking."""

    def __init__(
        self,
        embedding_engine: EmbeddingEngine,
        bm25_index: BM25Index,
        dense_weight: float = 0.65,
        rrf_k: int = 60,
    ):
        self.emb = embedding_engine
        self.bm25 = bm25_index
        self.alpha = dense_weight          # RRF dense weight
        self.rrf_k = rrf_k
        self._chunk_vectors: Optional[np.ndarray] = None
        self._indexed_chunks: List[Chunk] = []
        self._reranker = None
        self._try_load_reranker()

    def _try_load_reranker(self):
        try:
            from sentence_transformers import CrossEncoder
            self._reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
            print("  [HybridRetriever] Cross-encoder reranker loaded")
        except (ImportError, Exception):
            print("  [HybridRetriever] Cross-encoder not available — using RRF scores only")

    def index(self, chunks: List[Chunk]) -> None:
        self._indexed_chunks = chunks
        texts = [c.text for c in chunks]
        self._chunk_vectors = self.emb.encode(texts)
        self.bm25.build(chunks)
        print(f"  [HybridRetriever] Indexed {len(chunks)} chunks")

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        patient_id: Optional[str] = None,
        use_reranker: bool = True,
        candidate_k: int = 20,
    ) -> List[RetrievalResult]:
        """
        Full retrieval pipeline:
          1. Dense: top candidate_k by cosine similarity
          2. Sparse: top candidate_k by BM25
          3. RRF fusion
          4. Cross-encoder re-ranking (if available)
          5. Return top_k
        """
        # Patient-level hard filter (prevents cross-patient leakage)
        valid_chunks = self._indexed_chunks
        if patient_id:
            valid_chunks = [c for c in valid_chunks if c.patient_id == patient_id]
        if not valid_chunks:
            return []

        # ── Stage 1: Dual retrieval ──
        dense_ranked = self._dense_search(query, valid_chunks, candidate_k)
        sparse_ranked = self.bm25.query(query, candidate_k)
        # Filter sparse to valid_chunks
        valid_ids = {c.chunk_id for c in valid_chunks}
        sparse_ranked = [(c, s) for c, s in sparse_ranked if c.chunk_id in valid_ids]

        # ── Stage 2: RRF fusion ──
        fused = self._rrf(dense_ranked, sparse_ranked)

        # ── Stage 3: Cross-encoder re-ranking ──
        top_candidates = list(fused.values())[:min(candidate_k, len(fused))]
        if use_reranker and self._reranker and top_candidates:
            top_candidates = self._rerank(query, top_candidates)

        # Sort by final score, return top_k
        top_candidates.sort(key=lambda r: r.best_score, reverse=True)
        for rank, r in enumerate(top_candidates[:top_k]):
            r.final_rank = rank
        return top_candidates[:top_k]

    def _dense_search(
        self, query: str, chunks: List[Chunk], k: int
    ) -> List[Tuple[Chunk, float]]:
        if self._chunk_vectors is None or not chunks:
            return []
        # Get indices of valid chunks in original index
        valid_ids = {c.chunk_id for c in chunks}
        pairs = [
            (c, self._chunk_vectors[i])
            for i, c in enumerate(self._indexed_chunks)
            if c.chunk_id in valid_ids
        ]
        if not pairs:
            return []
        qvec = self.emb.encode([query])[0]
        vecs = np.array([v for _, v in pairs], dtype=np.float32)
        scores = np.dot(vecs, qvec)
        ranked = sorted(zip([c for c, _ in pairs], scores.tolist()), key=lambda x: x[1], reverse=True)
        return ranked[:k]

    def _rrf(
        self,
        dense: List[Tuple[Chunk, float]],
        sparse: List[Tuple[Chunk, float]],
    ) -> Dict[str, RetrievalResult]:
        results: Dict[str, RetrievalResult] = {}

        for rank, (chunk, score) in enumerate(dense):
            cid = chunk.chunk_id
            if cid not in results:
                results[cid] = RetrievalResult(chunk=chunk, dense_score=score)
            results[cid].rrf_score += self.alpha / (self.rrf_k + rank + 1)

        for rank, (chunk, score) in enumerate(sparse):
            cid = chunk.chunk_id
            if cid not in results:
                results[cid] = RetrievalResult(chunk=chunk)
            results[cid].sparse_score = score
            results[cid].rrf_score += (1 - self.alpha) / (self.rrf_k + rank + 1)

        return dict(sorted(results.items(), key=lambda x: x[1].rrf_score, reverse=True))

    def _rerank(self, query: str, results: List[RetrievalResult]) -> List[RetrievalResult]:
        pairs = [(query, r.chunk.text) for r in results]
        try:
            scores = self._reranker.predict(pairs)
            for r, s in zip(results, scores):
                r.rerank_score = float(s)
        except Exception:
            pass
        return results
