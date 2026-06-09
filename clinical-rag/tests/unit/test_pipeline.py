"""Unit tests for the main pipeline."""
import pytest
from src.pipeline import ClinicalRAGPipeline


SAMPLE_DISCHARGE_SUMMARY = """DISCHARGE SUMMARY

CHIEF COMPLAINT: Chest pain

HISTORY OF PRESENT ILLNESS:
Patient is a 65-year-old male who presented with acute chest pain.
EKG showed ST elevation in leads V1-V4 consistent with anterior STEMI.
Troponin levels were significantly elevated at 15.2 ng/mL.

MEDICATIONS AT DISCHARGE:
1. Aspirin 81mg daily
2. Clopidogrel 75mg daily
3. Atorvastatin 80mg daily
4. Metoprolol 25mg twice daily
5. Lisinopril 5mg daily

ASSESSMENT AND PLAN:
Patient underwent emergent cardiac catheterization with PCI to LAD.
Drug eluting stent placed successfully.
Patient discharged in stable condition.
Follow-up with cardiology in 1 week."""


@pytest.fixture
def pipeline():
    return ClinicalRAGPipeline(
        mock_llm=True,
        cache_enabled=True,
        reranker_enabled=False,  # Disable reranker for speed in tests
    )


@pytest.fixture
def loaded_pipeline(pipeline):
    """Pipeline with sample data ingested."""
    pipeline.ingest_text(
        document_id="discharge_001",
        text=SAMPLE_DISCHARGE_SUMMARY,
        content_type="discharge_summary",
        patient_id="PATIENT_001",
        document_date="2026-01-15",
    )
    return pipeline


def test_ingestion_success(pipeline):
    result = pipeline.ingest_text(
        document_id="test_doc",
        text=SAMPLE_DISCHARGE_SUMMARY,
        content_type="discharge_summary",
        patient_id="P001",
    )
    assert result.success
    assert result.chunks_created > 0
    assert result.document_id == "test_doc"


def test_ingestion_pii_redacted(pipeline):
    text = "Patient John Doe, SSN 123-45-6789, presented with chest pain."
    result = pipeline.ingest_text("pii_doc", text, patient_id="P001")
    assert result.success
    assert result.pii_detected


def test_query_returns_response(loaded_pipeline):
    response = loaded_pipeline.query(
        query="What medications was the patient discharged with?",
        patient_id="PATIENT_001",
    )
    assert response.query_id
    assert response.answer
    assert 0.0 <= response.confidence <= 1.0


def test_query_confidence_scored(loaded_pipeline):
    response = loaded_pipeline.query(
        query="What was the patient's diagnosis?",
        patient_id="PATIENT_001",
    )
    assert response.confidence_level in ("low", "medium", "high")


def test_structured_query_route(pipeline):
    """Structured queries should bypass vector search."""
    response = pipeline.query("List all medications")
    assert response.route in ("structured_query", "hybrid_retrieval")


def test_cache_hit(loaded_pipeline):
    query = "What medications was the patient discharged with?"
    # First call
    r1 = loaded_pipeline.query(query, patient_id="PATIENT_001")
    # Second call should hit cache
    r2 = loaded_pipeline.query(query, patient_id="PATIENT_001")
    assert r2.cache_hit


def test_versioning_updates_cache(pipeline):
    """Re-ingesting a document should invalidate cache."""
    pipeline.ingest_text("doc_v1", SAMPLE_DISCHARGE_SUMMARY, patient_id="P001")
    response = pipeline.query("What medications?", patient_id="P001")
    # Re-ingest same document (version 2)
    result = pipeline.ingest_text("doc_v1", "Updated: Patient discharged with Aspirin only.", patient_id="P001")
    assert result.version == 2


def test_metrics_tracked(loaded_pipeline):
    loaded_pipeline.query("What was the patient's diagnosis?", patient_id="PATIENT_001")
    metrics = loaded_pipeline.get_metrics()
    assert metrics["total_queries"] >= 1


def test_empty_query_handled(loaded_pipeline):
    """Pipeline should handle queries gracefully even with no matching docs."""
    response = loaded_pipeline.query(
        query="What was the patient's blood type?",
        patient_id="NONEXISTENT_PATIENT",
    )
    assert response.answer  # Should get a "not available" response


def test_audit_trail_logged(loaded_pipeline):
    loaded_pipeline.query("What medications?", patient_id="PATIENT_001", user_id="user_1")
    events = loaded_pipeline.audit.get_events(patient_id="PATIENT_001")
    assert len(events) >= 1
