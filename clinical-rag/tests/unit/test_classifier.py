"""Unit tests for query classifier."""
import pytest
from src.query.classifier import QueryClassifier, QueryType


@pytest.fixture
def classifier():
    return QueryClassifier()


def test_structured_query_medications(classifier):
    result = classifier.classify("List all medications the patient is taking")
    assert result.query_type == QueryType.STRUCTURED_QUERY
    assert result.requires_structured_path


def test_structured_query_labs(classifier):
    result = classifier.classify("Show all lab results from last week")
    assert result.query_type == QueryType.STRUCTURED_QUERY


def test_explanation_query(classifier):
    result = classifier.classify("Why was the patient started on antibiotics?")
    assert result.query_type == QueryType.EXPLANATION


def test_comparison_query(classifier):
    result = classifier.classify("How did blood pressure change from admission to discharge?")
    assert result.query_type == QueryType.COMPARISON


def test_summarization_query(classifier):
    result = classifier.classify("Summarize the hospital course for this patient")
    assert result.query_type == QueryType.SUMMARIZATION


def test_temporal_query(classifier):
    result = classifier.classify("What happened on January 15th?")
    assert result.query_type == QueryType.TEMPORAL


def test_factual_lookup_query(classifier):
    result = classifier.classify("What was the patient's diagnosis?")
    # Should be factual_lookup or reasonable match
    assert result.query_type in (QueryType.FACTUAL_LOOKUP, QueryType.EXPLANATION)


def test_multi_hop_query(classifier):
    result = classifier.classify("Was the treatment consistent with the diagnosis?")
    assert result.query_type == QueryType.MULTI_HOP


def test_confidence_range(classifier):
    result = classifier.classify("What medications was the patient on?")
    assert 0.0 <= result.confidence <= 1.0


def test_complexity_assigned(classifier):
    result = classifier.classify("List all medications")
    assert result.estimated_complexity in ("simple", "medium", "complex")
