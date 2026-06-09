"""
Hybrid retrieval: fuses dense and sparse results using Reciprocal Rank Fusion (RRF).
"""
from __future__ import annotations

from typing import Dict, List, Optional

from ..ingestion.chunking import DocumentChunk
from ..ingestion.embedding import SearchResult
from .dense import DenseRetriever
from .sparse import SparseRetriever


class HybridRetriever:
    """
    Combines dense (vector) and sparse (BM25) retrieval via Reciprocal Rank Fusion.
    Applies patient-level filtering as a hard constraint.
    """

    def __init__(
        self,
        dense: DenseRetriever,
        sparse: SparseRetriever,
        dense_weight: float = 0.7,
        sparse_weight: float = 0.3,
        rrf_k: int = 60,
    ):
        self.dense = dense
        self.sparse = sparse
        self.dense_weight = dense_weight
        self.sparse_weight = sparse_weight
        self.rrf_k = rrf_k

    def retrieve(
        self,
        query: str,
        top_k: int = 10,
        patient_id: Optional[str] = None,
        document_type: Optional[str] = None,
        use_dense: bool = True,
        use_sparse: bool = True,
        min_score: float = 0.0,
    ) -> List[SearchResult]:
        """Retrieve using hybrid fusion with patient-level filtering."""
        dense_results: List[SearchResult] = []
        sparse_results: List[SearchResult] = []

        if use_dense:
            dense_results = self.dense.retrieve(
                query=query,
                top_k=top_k * 2,
                patient_id=patient_id,
                document_type=document_type,
            )

        if use_sparse:
            sparse_results = self.sparse.retrieve(
                query=query,
                top_k=top_k * 2,
                patient_id=patient_id,
            )

        if not dense_results and not sparse_results:
            return []

        # Only dense or only sparse
        if not sparse_results:
            return dense_results[:top_k]
        if not dense_results:
            return sparse_results[:top_k]

        return self._reciprocal_rank_fusion(dense_results, sparse_results, top_k)

    def _reciprocal_rank_fusion(
        self,
        dense_results: List[SearchResult],
        sparse_results: List[SearchResult],
        top_k: int,
    ) -> List[SearchResult]:
        """Fuse two ranked lists using Reciprocal Rank Fusion."""
        scores: Dict[str, float] = {}
        chunk_map: Dict[str, DocumentChunk] = {}

        # Dense contribution
        for rank, result in enumerate(dense_results):
            cid = result.chunk.chunk_id
            rrf_score = self.dense_weight / (self.rrf_k + rank + 1)
            scores[cid] = scores.get(cid, 0.0) + rrf_score
            chunk_map[cid] = result.chunk

        # Sparse contribution
        for rank, result in enumerate(sparse_results):
            cid = result.chunk.chunk_id
            rrf_score = self.sparse_weight / (self.rrf_k + rank + 1)
            scores[cid] = scores.get(cid, 0.0) + rrf_score
            chunk_map[cid] = result.chunk

        # Sort by fused score
        sorted_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        results = []
        for final_rank, (cid, score) in enumerate(sorted_items[:top_k]):
            results.append(SearchResult(
                chunk=chunk_map[cid],
                score=score,
                rank=final_rank,
            ))
        return results
