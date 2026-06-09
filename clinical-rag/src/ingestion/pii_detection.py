"""
PII Detection and Pseudonymization (Layer 1 of 3-layer protection).
Detects and replaces PII before storage in vector database.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class PIIEntity:
    entity_type: str  # patient_id, provider_name, ssn, phone, email, date, mrn
    start: int
    end: int
    original_text: str
    pseudonym: str


@dataclass
class PIIResult:
    original_document_id: str
    pseudonymized_content: str
    pii_detected: bool
    pii_entities: List[PIIEntity]
    reversible: bool = False  # Pseudonymization is one-way


# Compiled PII patterns
_PII_PATTERNS = [
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("phone", re.compile(r"\(?\d{3}\)?[\s\-\.]\d{3}[\s\-\.]\d{4}\b")),
    ("email", re.compile(r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b")),
    ("mrn", re.compile(r"\bMRN[:\s]?\s*\d{5,10}\b", re.IGNORECASE)),
    ("dob", re.compile(
        r"\b(?:DOB|Date of Birth|Birth Date)[:\s]+\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}\b",
        re.IGNORECASE,
    )),
    ("specific_date", re.compile(
        r"\b(?:January|February|March|April|May|June|July|August|September|October|"
        r"November|December)\s+\d{1,2},?\s+\d{4}\b",
        re.IGNORECASE,
    )),
    ("date_numeric", re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b")),
    ("age_over_89", re.compile(r"\b(9\d|1[01]\d)\s*(?:year|yr)s?\s*old\b", re.IGNORECASE)),
    ("device_id", re.compile(r"\b(?:Serial|Device)\s*(?:No|Number|#)[:\s]+[A-Z0-9\-]{6,20}\b", re.IGNORECASE)),
]

# Patterns for provider/patient name detection (simple heuristic)
_NAME_IN_CONTEXT = re.compile(
    r"\b(?:Dr\.|Doctor|Physician|Patient|Pt\.?)[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})",
)


class PIIDetector:
    """
    Detects PII using regex patterns and pseudonymizes using consistent SHA-256 hashing.

    Layer 1 of 3-layer PII protection:
      Layer 1 (this): Ingestion-time pseudonymization
      Layer 2: Prompt assembly PII guard (see post_processing/validation.py)
      Layer 3: Output validation PII scan (see post_processing/validation.py)
    """

    def __init__(self, salt: str = "default_salt_change_me", enabled: bool = True):
        self.salt = salt
        self.enabled = enabled
        # Consistent mapping: original -> pseudonym (in-memory cache per session)
        self._pseudonym_cache: Dict[str, str] = {}

    def process(self, document_id: str, text: str) -> PIIResult:
        """Detect and pseudonymize PII in a document."""
        if not self.enabled:
            return PIIResult(
                original_document_id=document_id,
                pseudonymized_content=text,
                pii_detected=False,
                pii_entities=[],
            )

        entities = self._detect_all(text)
        pseudonymized = self._replace_pii(text, entities)

        return PIIResult(
            original_document_id=document_id,
            pseudonymized_content=pseudonymized,
            pii_detected=len(entities) > 0,
            pii_entities=entities,
        )

    def scan_output(self, text: str) -> Tuple[bool, List[str]]:
        """
        Layer 3: Scan LLM output for PII leakage.
        Returns (detected: bool, found_types: list).
        """
        entities = self._detect_all(text)
        if entities:
            found_types = list({e.entity_type for e in entities})
            return True, found_types
        return False, []

    def _detect_all(self, text: str) -> List[PIIEntity]:
        entities: List[PIIEntity] = []

        # Regex-based detection
        for entity_type, pattern in _PII_PATTERNS:
            for m in pattern.finditer(text):
                pseudonym = self._make_pseudonym(entity_type, m.group())
                entities.append(PIIEntity(
                    entity_type=entity_type,
                    start=m.start(),
                    end=m.end(),
                    original_text=m.group(),
                    pseudonym=pseudonym,
                ))

        # Name-in-context detection
        for m in _NAME_IN_CONTEXT.finditer(text):
            name = m.group(1)
            pseudonym = self._make_pseudonym("person_name", name)
            entities.append(PIIEntity(
                entity_type="person_name",
                start=m.start(1),
                end=m.end(1),
                original_text=name,
                pseudonym=pseudonym,
            ))

        # Sort by position, deduplicate overlapping
        entities.sort(key=lambda e: e.start)
        return self._deduplicate(entities)

    def _replace_pii(self, text: str, entities: List[PIIEntity]) -> str:
        """Replace PII in text with pseudonyms, processing right-to-left to preserve offsets."""
        result = text
        for entity in reversed(entities):
            result = result[: entity.start] + entity.pseudonym + result[entity.end :]
        return result

    def _make_pseudonym(self, entity_type: str, original: str) -> str:
        """Create a consistent pseudonym using SHA-256 hashing."""
        key = f"{self.salt}:{entity_type}:{original}"
        hash_val = hashlib.sha256(key.encode()).hexdigest()[:8]

        type_prefixes = {
            "ssn": "[SSN_REDACTED]",
            "phone": "[PHONE_REDACTED]",
            "email": "[EMAIL_REDACTED]",
            "mrn": f"[MRN_{hash_val}]",
            "dob": "[DOB_REDACTED]",
            "specific_date": "[DATE]",
            "date_numeric": "[DATE]",
            "age_over_89": "[AGE>89]",
            "device_id": f"[DEVICE_{hash_val}]",
            "person_name": f"[PERSON_{hash_val}]",
        }
        return type_prefixes.get(entity_type, f"[{entity_type.upper()}_{hash_val}]")

    def _deduplicate(self, entities: List[PIIEntity]) -> List[PIIEntity]:
        """Remove overlapping entities, keeping the first (longest match wins if equal start)."""
        if not entities:
            return entities
        result = [entities[0]]
        for entity in entities[1:]:
            prev = result[-1]
            if entity.start >= prev.end:
                result.append(entity)
        return result
