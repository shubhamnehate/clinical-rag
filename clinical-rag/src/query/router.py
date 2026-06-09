"""Query router: maps query type to retrieval parameters and strategy."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

from .classifier import ClassificationResult, QueryType


@dataclass
class RouteDecision:
    route: str  # hybrid_retrieval | structured_query | multi_hop | document_level
    parameters: Dict[str, Any] = field(default_factory=dict)
    estimated_latency_ms: int = 200


_ROUTE_PARAMS: Dict[QueryType, Dict[str, Any]] = {
    QueryType.FACTUAL_LOOKUP: {
        "k": 5, "rerank": True, "use_dense": True, "use_sparse": True,
        "route": "hybrid_retrieval", "latency": 150,
    },
    QueryType.EXPLANATION: {
        "k": 10, "rerank": True, "use_dense": True, "use_sparse": False,
        "route": "hybrid_retrieval", "latency": 200,
    },
    QueryType.COMPARISON: {
        "k": 20, "rerank": True, "use_dense": True, "use_sparse": True,
        "temporal_sort": True, "route": "hybrid_retrieval", "latency": 300,
    },
    QueryType.MULTI_HOP: {
        "k": 15, "rerank": True, "iterative": True, "max_hops": 3,
        "route": "multi_hop", "latency": 500,
    },
    QueryType.SUMMARIZATION: {
        "k": 50, "rerank": False, "document_level": True,
        "route": "document_level", "latency": 400,
    },
    QueryType.TEMPORAL: {
        "k": 10, "rerank": True, "date_filter": True,
        "route": "hybrid_retrieval", "latency": 200,
    },
    QueryType.STRUCTURED_QUERY: {
        "use_vector_search": False, "use_structured_db": True,
        "route": "structured_query", "latency": 50,
    },
}


class QueryRouter:
    def route(self, classification: ClassificationResult) -> RouteDecision:
        params = _ROUTE_PARAMS.get(classification.query_type, _ROUTE_PARAMS[QueryType.FACTUAL_LOOKUP])
        return RouteDecision(
            route=params["route"],
            parameters={k: v for k, v in params.items() if k not in ("route", "latency")},
            estimated_latency_ms=params.get("latency", 200),
        )
