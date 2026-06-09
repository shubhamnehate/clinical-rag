"""Unit tests for document loaders."""
import json
import pytest
from src.ingestion.loaders import DocumentLoader


@pytest.fixture
def loader():
    return DocumentLoader()


def test_load_from_text(loader):
    doc = loader.load_from_text("doc1", "Patient has chest pain.", "clinical_note")
    assert doc.document_id == "doc1"
    assert doc.text_content == "Patient has chest pain."
    assert doc.content_type == "clinical_note"
    assert doc.load_error is None


def test_detect_clinical_note_type(loader):
    text = "HISTORY OF PRESENT ILLNESS: Patient presents with cough."
    doc = loader.load_from_text("doc1", text)
    assert doc.content_type == "clinical_note"


def test_detect_radiology_type(loader):
    text = "FINDINGS: No acute findings. IMPRESSION: Normal chest X-ray."
    content_type = loader._detect_clinical_type(text)
    assert content_type == "radiology_report"


def test_unsupported_extension(loader, tmp_path):
    f = tmp_path / "test.xyz"
    f.write_text("test")
    doc = loader.load(str(f))
    assert doc.load_error is not None


def test_fhir_to_text_patient(loader):
    resource = {
        "resourceType": "Patient",
        "id": "P001",
        "name": [{"given": ["John"], "family": "Doe"}],
        "birthDate": "1960-01-15",
        "gender": "male",
    }
    text = loader._fhir_to_text(resource)
    assert "Patient" in text
    assert "John" in text or "Doe" in text


def test_fhir_to_text_medication(loader):
    resource = {
        "resourceType": "MedicationRequest",
        "id": "med1",
        "medicationCodeableConcept": {"text": "Metformin 1000mg"},
        "dosageInstruction": [{"text": "twice daily"}],
    }
    text = loader._fhir_to_text(resource)
    assert "Metformin" in text


def test_hl7_basic_parse(loader):
    hl7_msg = "MSH|^~\\&|HIS|Hospital|LAB|Lab|20260101||ORU^R01|MSG001|P|2.5\nPID|||MRN123||Doe^John||19600115|M\nOBX|1|NM|GLUCOSE^Glucose|126|mg/dL"
    structured = loader._parse_hl7_basic(hl7_msg)
    assert "patient_name" in structured
    assert len(structured.get("observations", [])) >= 1
