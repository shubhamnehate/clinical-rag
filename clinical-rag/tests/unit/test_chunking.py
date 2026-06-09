"""Unit tests for the chunking engine."""
import pytest
from src.ingestion.chunking import ChunkingEngine


@pytest.fixture
def chunker():
    return ChunkingEngine(
        target_size_tokens=100,
        max_size_tokens=200,
        min_size_tokens=10,
        overlap_tokens=20,
    )


SAMPLE_CLINICAL_NOTE = """CHIEF COMPLAINT:
Patient presents with chest pain and shortness of breath.

HISTORY OF PRESENT ILLNESS:
A 65-year-old male with a history of hypertension and diabetes mellitus presented
to the emergency department with acute onset chest pain radiating to the left arm.
The pain started approximately 2 hours prior to arrival. Associated symptoms include
diaphoresis and nausea. No fever or chills.

MEDICATIONS:
1. Metformin 1000mg twice daily
2. Lisinopril 10mg once daily
3. Aspirin 81mg once daily

ASSESSMENT AND PLAN:
1. Chest pain - rule out ACS, obtain ECG and troponins
2. Hypertension - continue current medications
3. Diabetes - monitor blood glucose"""


def test_chunks_clinical_note(chunker):
    chunks = chunker.chunk("doc1", SAMPLE_CLINICAL_NOTE, patient_id="P001")
    assert len(chunks) > 0
    for chunk in chunks:
        assert chunk.parent_doc_id == "doc1"
        assert chunk.patient_id == "P001"
        assert chunk.token_count >= 10


def test_sections_detected(chunker):
    chunks = chunker.chunk("doc1", SAMPLE_CLINICAL_NOTE)
    sections = {c.section for c in chunks}
    assert len(sections) > 1  # Multiple sections detected


def test_chunk_ids_unique(chunker):
    chunks = chunker.chunk("doc1", SAMPLE_CLINICAL_NOTE)
    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids))


def test_empty_text(chunker):
    chunks = chunker.chunk("doc1", "")
    assert chunks == []


def test_short_text(chunker):
    chunks = chunker.chunk("doc1", "Patient has fever.")
    # Short text may produce 0 chunks (below min_size) or 1 chunk
    assert len(chunks) <= 1


def test_version_tracking(chunker):
    chunks = chunker.chunk("doc1", SAMPLE_CLINICAL_NOTE, version=2)
    for chunk in chunks:
        assert chunk.version == 2


def test_document_type_propagated(chunker):
    chunks = chunker.chunk("doc1", SAMPLE_CLINICAL_NOTE, document_type="discharge_summary")
    for chunk in chunks:
        assert chunk.document_type == "discharge_summary"
