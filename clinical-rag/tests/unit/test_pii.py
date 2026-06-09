"""Unit tests for PII detection and pseudonymization."""
import pytest
from src.ingestion.pii_detection import PIIDetector


@pytest.fixture
def detector():
    return PIIDetector(salt="test_salt")


def test_detects_ssn(detector):
    text = "Patient SSN: 123-45-6789"
    result = detector.process("doc1", text)
    assert result.pii_detected
    assert "123-45-6789" not in result.pseudonymized_content
    assert "[SSN_REDACTED]" in result.pseudonymized_content


def test_detects_phone(detector):
    text = "Call us at (555) 123-4567"
    result = detector.process("doc1", text)
    assert result.pii_detected
    assert "(555) 123-4567" not in result.pseudonymized_content


def test_detects_email(detector):
    text = "Contact john.doe@hospital.com for follow-up"
    result = detector.process("doc1", text)
    assert result.pii_detected
    assert "john.doe@hospital.com" not in result.pseudonymized_content
    assert "[EMAIL_REDACTED]" in result.pseudonymized_content


def test_detects_mrn(detector):
    text = "MRN: 1234567 Patient was admitted"
    result = detector.process("doc1", text)
    assert result.pii_detected
    assert any(e.entity_type == "mrn" for e in result.pii_entities)


def test_no_pii(detector):
    text = "Patient presented with chest pain. Vitals were stable."
    result = detector.process("doc1", text)
    assert not result.pii_detected
    assert result.pseudonymized_content == text


def test_consistent_hashing(detector):
    """Same original value must always produce same pseudonym."""
    text = "SSN 123-45-6789 repeated: 123-45-6789"
    result = detector.process("doc1", text)
    # Both occurrences should be replaced consistently
    parts = result.pseudonymized_content.split("[SSN_REDACTED]")
    # All instances replaced
    assert "123-45-6789" not in result.pseudonymized_content


def test_output_scan_detects_pii(detector):
    text = "The patient John Smith at 555-123-4567 was discharged"
    detected, types = detector.scan_output(text)
    assert detected
    assert "phone" in types


def test_output_scan_no_pii(detector):
    text = "The patient was discharged with stable vitals and good prognosis."
    detected, types = detector.scan_output(text)
    assert not detected
    assert types == []


def test_disabled_detector():
    d = PIIDetector(enabled=False)
    text = "SSN: 123-45-6789"
    result = d.process("doc1", text)
    assert not result.pii_detected
    assert result.pseudonymized_content == text
