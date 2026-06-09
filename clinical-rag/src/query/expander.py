"""
Query expander: adds medical synonyms, abbreviations, and related terms.
Uses a built-in medical terminology dictionary (UMLS-inspired).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class ExpandedTerm:
    term: str
    weight: float
    term_type: str  # original, synonym, abbreviation, related


@dataclass
class ExpandedQuery:
    original_query: str
    expanded_terms: List[ExpandedTerm]
    expanded_query_string: str  # Combined string for dense search

    def weighted_terms(self, min_weight: float = 0.7) -> List[str]:
        return [t.term for t in self.expanded_terms if t.weight >= min_weight]


# Medical terminology: term -> (synonyms, abbreviations, related_concepts)
_MEDICAL_DICT: Dict[str, Tuple[List[str], List[str], List[str]]] = {
    "myocardial infarction": (
        ["heart attack", "cardiac infarction", "MI"],
        ["MI", "AMI", "STEMI", "NSTEMI"],
        ["chest pain", "troponin", "ecg changes", "coronary artery"],
    ),
    "heart attack": (
        ["myocardial infarction", "cardiac infarction"],
        ["MI", "AMI"],
        ["chest pain", "troponin", "ecg"],
    ),
    "diabetes": (
        ["diabetes mellitus", "diabetic"],
        ["DM", "T2DM", "T1DM"],
        ["glucose", "insulin", "hba1c", "blood sugar", "glycemic"],
    ),
    "hypertension": (
        ["high blood pressure", "elevated blood pressure"],
        ["HTN", "BP"],
        ["blood pressure", "systolic", "diastolic", "antihypertensive"],
    ),
    "blood pressure": (
        ["arterial pressure", "bp reading"],
        ["BP", "SBP", "DBP"],
        ["hypertension", "hypotension", "systolic", "diastolic"],
    ),
    "medication": (
        ["drug", "medicine", "prescription", "pharmaceutical"],
        ["med", "rx", "meds"],
        ["dosage", "dose", "frequency", "route of administration"],
    ),
    "discharge": (
        ["discharged from hospital", "release from hospital"],
        ["d/c"],
        ["discharge summary", "discharge medications", "follow-up"],
    ),
    "lab": (
        ["laboratory", "lab result", "laboratory test", "blood test"],
        ["labs"],
        ["specimen", "serum", "plasma", "result"],
    ),
    "vital signs": (
        ["vitals", "vital measurements"],
        ["VS"],
        ["blood pressure", "heart rate", "temperature", "oxygen saturation", "respiratory rate"],
    ),
    "heart rate": (
        ["pulse", "cardiac rate"],
        ["HR", "pulse rate"],
        ["bradycardia", "tachycardia", "rhythm"],
    ),
    "oxygen saturation": (
        ["o2 saturation", "spo2", "oxygen level"],
        ["SpO2", "O2 sat"],
        ["hypoxia", "oxygen therapy", "saturation"],
    ),
    "ecg": (
        ["electrocardiogram", "ekg", "cardiac tracing"],
        ["EKG", "ECG"],
        ["rhythm", "qrs", "st segment", "t wave"],
    ),
    "pneumonia": (
        ["lung infection", "pulmonary infection"],
        ["PNA"],
        ["chest xray", "infiltrate", "antibiotic", "respiratory"],
    ),
    "surgery": (
        ["operation", "surgical procedure", "operative procedure"],
        ["OR", "procedure"],
        ["anesthesia", "incision", "post-op", "pre-op"],
    ),
    "allergy": (
        ["allergic reaction", "hypersensitivity"],
        ["NKDA", "NKA"],
        ["anaphylaxis", "adverse reaction", "intolerance"],
    ),
}

# Abbreviation expansion table
_ABBREVIATIONS: Dict[str, str] = {
    r"\bBP\b": "blood pressure",
    r"\bHR\b": "heart rate",
    r"\bRR\b": "respiratory rate",
    r"\bSpO2\b": "oxygen saturation",
    r"\bDM\b": "diabetes mellitus",
    r"\bHTN\b": "hypertension",
    r"\bMI\b": "myocardial infarction",
    r"\bCHF\b": "congestive heart failure",
    r"\bCOPD\b": "chronic obstructive pulmonary disease",
    r"\bDVT\b": "deep vein thrombosis",
    r"\bPE\b": "pulmonary embolism",
    r"\bUTI\b": "urinary tract infection",
    r"\bCAD\b": "coronary artery disease",
    r"\bCVA\b": "cerebrovascular accident stroke",
    r"\bTIA\b": "transient ischemic attack",
    r"\bHbA1c\b": "hemoglobin a1c glycated hemoglobin",
    r"\bECG\b": "electrocardiogram",
    r"\bEKG\b": "electrocardiogram",
    r"\bMRI\b": "magnetic resonance imaging",
    r"\bCT\b": "computed tomography",
    r"\bd/c\b": "discharge",
    r"\bRx\b": "prescription medication",
    r"\bH&P\b": "history and physical",
    r"\bHPI\b": "history of present illness",
}


class QueryExpander:
    """Expand clinical queries with medical synonyms and abbreviations."""

    def __init__(self, enabled: bool = True, max_terms: int = 10, min_confidence: float = 0.7):
        self.enabled = enabled
        self.max_terms = max_terms
        self.min_confidence = min_confidence

    def expand(self, query: str) -> ExpandedQuery:
        if not self.enabled:
            return ExpandedQuery(
                original_query=query,
                expanded_terms=[ExpandedTerm(query, 1.0, "original")],
                expanded_query_string=query,
            )

        terms: List[ExpandedTerm] = [ExpandedTerm(query, 1.0, "original")]
        query_lower = query.lower()

        # Abbreviation expansion
        expanded_query = query
        for abbr_pattern, expansion in _ABBREVIATIONS.items():
            if re.search(abbr_pattern, query, re.IGNORECASE):
                terms.append(ExpandedTerm(expansion, 0.85, "abbreviation"))
                expanded_query = re.sub(abbr_pattern, f"{re.search(abbr_pattern, query).group()} {expansion}", expanded_query, flags=re.IGNORECASE)

        # Medical synonym expansion
        for term, (synonyms, abbreviations, related) in _MEDICAL_DICT.items():
            if term in query_lower:
                for syn in synonyms[:2]:
                    terms.append(ExpandedTerm(syn, 0.9, "synonym"))
                for abbr in abbreviations[:2]:
                    terms.append(ExpandedTerm(abbr, 0.85, "abbreviation"))
                for rel in related[:2]:
                    terms.append(ExpandedTerm(rel, 0.7, "related"))

        # Deduplicate
        seen = set()
        unique_terms = []
        for t in terms:
            key = t.term.lower()
            if key not in seen:
                seen.add(key)
                unique_terms.append(t)

        # Limit
        unique_terms = unique_terms[:self.max_terms]

        # Build expanded query string (for dense search)
        significant = [t.term for t in unique_terms if t.weight >= self.min_confidence and t.term_type != "related"]
        expanded_str = " ".join(dict.fromkeys([query] + significant))

        return ExpandedQuery(
            original_query=query,
            expanded_terms=unique_terms,
            expanded_query_string=expanded_str,
        )
