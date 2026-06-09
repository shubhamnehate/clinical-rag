"""In-memory metrics collection (swap for Prometheus in production)."""
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class QueryMetrics:
    query_id: str
    latency_ms: float
    confidence: float
    cache_hit: bool
    retry_count: int
    retrieval_count: int
    pii_detected_in_output: bool = False
    timestamp: float = field(default_factory=time.time)


class MetricsCollector:
    """Tracks system metrics for monitoring and alerting."""

    def __init__(self):
        self._queries: List[QueryMetrics] = []
        self._counters: Dict[str, int] = defaultdict(int)
        self._histograms: Dict[str, List[float]] = defaultdict(list)

    def record_query(self, metrics: QueryMetrics) -> None:
        self._queries.append(metrics)
        self._counters["total_queries"] += 1
        self._histograms["latency_ms"].append(metrics.latency_ms)
        self._histograms["confidence"].append(metrics.confidence)
        if metrics.cache_hit:
            self._counters["cache_hits"] += 1
        if metrics.pii_detected_in_output:
            self._counters["pii_output_detections"] += 1
        if metrics.retry_count > 0:
            self._counters["queries_with_retries"] += 1

    def increment(self, name: str, value: int = 1) -> None:
        self._counters[name] += value

    def get_summary(self) -> Dict:
        total = self._counters["total_queries"]
        latencies = self._histograms["latency_ms"]
        confidences = self._histograms["confidence"]

        return {
            "total_queries": total,
            "cache_hit_rate": self._counters["cache_hits"] / max(total, 1),
            "avg_latency_ms": sum(latencies) / max(len(latencies), 1),
            "p95_latency_ms": sorted(latencies)[int(0.95 * len(latencies))] if latencies else 0,
            "avg_confidence": sum(confidences) / max(len(confidences), 1),
            "pii_output_detections": self._counters["pii_output_detections"],
            "queries_with_retries": self._counters["queries_with_retries"],
            "counters": dict(self._counters),
        }
