"""
Query classifier: determines query type to route to the correct retrieval strategy.
Runs BEFORE any retrieval (critical design requirement).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class QueryType(str, Enum):
    FACTUAL_LOOKUP = "factual_lookup"
    EXPLANATION = "explanation"
    COMPARISON = "comparison"
    MULTI_HOP = "multi_hop"
    SUMMARIZATION = "summarization"
    TEMPORAL = "temporal"
    STRUCTURED_QUERY = "structured_query"


@dataclass
class ClassificationResult:
    query_type: QueryType
    confidence: float
    reasoning: str
    requires_structured_path: bool
    estimated_complexity: str  # simple, medium, complex


# Keyword-based classification rules
_RULES = [
    (QueryType.STRUCTURED_QUERY, [
        r"\ball\b.*(medication|lab|result|test|value|vital)",
        r"\blist\b.*(medication|lab|diagnosis|condition|procedure)",
        r"\bshow\b.*(lab|result|medication|vital|value)",
        r"\bhow many\b",
        r"\bcount\b",
        r"\blatest\b.*(lab|result|value|vital)",
        r"\bmost recent\b",
    ], True, "simple"),

    (QueryType.TEMPORAL, [
        r"\bwhen\b",
        r"\bon\s+(?:january|february|march|april|may|june|july|august|september|october|november|december)",
        r"\bon\s+\d{1,2}/\d{1,2}",
        r"\blast\s+(?:week|month|year|day)",
        r"\bthis\s+(?:week|month|year)",
        r"\bafter\b",
        r"\bbefore\b",
        r"\btimeline\b",
        r"\bchronol",
    ], False, "medium"),

    (QueryType.COMPARISON, [
        r"\bcompare\b",
        r"\bdifference\b",
        r"\bchange\b.*(from|to|over time)",
        r"\bhow.*(changed|different|improved|worsened)",
        r"\badmission.*discharge",
        r"\bdischarge.*admission",
        r"\btrend\b",
        r"\bover time\b",
        r"\bbefore.*after\b",
    ], False, "complex"),

    (QueryType.MULTI_HOP, [
        r"\bconsistent\b",
        r"\brelated to\b",
        r"\bcaused by\b",
        r"\bbecause of\b",
        r"\bconnection between\b",
        r"\brelationship between\b",
        r"\bwas the.*(treatment|therapy|medication).*(appropriate|correct|consistent)",
        r"\bdid.*(lead to|cause|result in)",
    ], False, "complex"),

    (QueryType.SUMMARIZATION, [
        r"\bsummar",
        r"\boverview\b",
        r"\bbrief\b",
        r"\bwhat happened\b",
        r"\bhospital course\b",
        r"\bmedical history\b",
        r"\boverall\b",
        r"\bin general\b",
    ], False, "complex"),

    (QueryType.EXPLANATION, [
        r"\bwhy\b",
        r"\bhow\b.*(?:was|were|did|does)",
        r"\bexplain\b",
        r"\breason\b",
        r"\breason(?:ing)? for\b",
        r"\bindication\b",
        r"\bstarted on\b",
        r"\bprescribed\b",
    ], False, "medium"),

    (QueryType.FACTUAL_LOOKUP, [
        r"\bwhat\b.*(medication|drug|diagnosis|condition|test|lab|vital|dose|level)",
        r"\bwhich\b",
        r"\bwho\b",
        r"\bwhat is\b",
        r"\bwhat was\b",
        r"\btell me\b",
        r"\bfind\b",
    ], False, "simple"),
]

_COMPILED_RULES = [
    (qtype, [re.compile(p, re.IGNORECASE) for p in patterns], structured, complexity)
    for qtype, patterns, structured, complexity in _RULES
]


class QueryClassifier:
    """
    Keyword-based query classifier.
    Runs before ALL retrieval operations (required from day 1).
    """

    def classify(self, query: str) -> ClassificationResult:
        query_lower = query.lower()
        best_type = QueryType.FACTUAL_LOOKUP
        best_confidence = 0.4
        best_structured = False
        best_complexity = "simple"
        best_reasoning = "Default: factual lookup (no strong signals)"

        for qtype, patterns, structured, complexity in _COMPILED_RULES:
            matches = sum(1 for p in patterns if p.search(query_lower))
            if matches == 0:
                continue
            confidence = min(0.95, 0.5 + matches * 0.15)
            if confidence > best_confidence:
                best_type = qtype
                best_confidence = confidence
                best_structured = structured
                best_complexity = complexity
                matched = [p.pattern for p in patterns if p.search(query_lower)]
                best_reasoning = f"Matched {matches} signals: {matched[:2]}"

        return ClassificationResult(
            query_type=best_type,
            confidence=best_confidence,
            reasoning=best_reasoning,
            requires_structured_path=best_structured,
            estimated_complexity=best_complexity,
        )
