"""Document loaders for Text, PDF, DICOM, HL7, and FHIR formats."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class LoadedDocument:
    """Represents a loaded clinical document before PII processing."""
    document_id: str
    file_path: str
    content_type: str  # clinical_note, radiology_report, lab_report, fhir_resource, hl7_message
    text_content: str
    structured_data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    requires_structured_path: bool = False
    load_error: Optional[str] = None

    def __post_init__(self):
        if "loaded_at" not in self.metadata:
            self.metadata["loaded_at"] = datetime.utcnow().isoformat()


class DocumentLoader:
    """
    Loads clinical documents from various formats.
    Supports: .txt, .rtf, .pdf, .dcm (DICOM), .hl7, .json (FHIR)
    """

    SUPPORTED_EXTENSIONS = {
        ".txt": "text",
        ".rtf": "text",
        ".pdf": "pdf",
        ".dcm": "dicom",
        ".hl7": "hl7",
        ".json": "fhir",
    }

    def load(self, file_path: str) -> LoadedDocument:
        path = Path(file_path)
        ext = path.suffix.lower()
        doc_id = path.stem + "_" + str(abs(hash(str(path))))[:8]

        if ext not in self.SUPPORTED_EXTENSIONS:
            return LoadedDocument(
                document_id=doc_id,
                file_path=file_path,
                content_type="unknown",
                text_content="",
                load_error=f"Unsupported file extension: {ext}",
            )

        loader_type = self.SUPPORTED_EXTENSIONS[ext]
        try:
            if loader_type == "text":
                return self._load_text(doc_id, file_path)
            elif loader_type == "pdf":
                return self._load_pdf(doc_id, file_path)
            elif loader_type == "dicom":
                return self._load_dicom(doc_id, file_path)
            elif loader_type == "hl7":
                return self._load_hl7(doc_id, file_path)
            elif loader_type == "fhir":
                return self._load_fhir(doc_id, file_path)
        except Exception as e:
            return LoadedDocument(
                document_id=doc_id,
                file_path=file_path,
                content_type="unknown",
                text_content="",
                load_error=str(e),
            )

    def load_from_text(self, doc_id: str, text: str, content_type: str = "clinical_note",
                       metadata: Optional[Dict] = None) -> LoadedDocument:
        """Load a document directly from a text string (useful for testing)."""
        return LoadedDocument(
            document_id=doc_id,
            file_path="<memory>",
            content_type=content_type,
            text_content=text,
            metadata=metadata or {},
        )

    def _load_text(self, doc_id: str, file_path: str) -> LoadedDocument:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        return LoadedDocument(
            document_id=doc_id,
            file_path=file_path,
            content_type=self._detect_clinical_type(text),
            text_content=text,
            metadata={"file_size": os.path.getsize(file_path)},
        )

    def _load_pdf(self, doc_id: str, file_path: str) -> LoadedDocument:
        try:
            import pypdf
            reader = pypdf.PdfReader(file_path)
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except ImportError:
            try:
                import PyPDF2
                with open(file_path, "rb") as f:
                    reader = PyPDF2.PdfReader(f)
                    text = "\n".join(
                        page.extract_text() or "" for page in reader.pages
                    )
            except ImportError:
                text = f"[PDF content from {file_path} - install pypdf for extraction]"
        return LoadedDocument(
            document_id=doc_id,
            file_path=file_path,
            content_type=self._detect_clinical_type(text),
            text_content=text,
            metadata={"format": "pdf"},
        )

    def _load_dicom(self, doc_id: str, file_path: str) -> LoadedDocument:
        """
        Extract DICOM metadata as structured fields.
        Treat text reports as free text, metadata as structured.
        """
        try:
            import pydicom
            ds = pydicom.dcmread(file_path, stop_before_pixels=True)
            structured = {
                "patient_id": str(getattr(ds, "PatientID", "")),
                "study_date": str(getattr(ds, "StudyDate", "")),
                "modality": str(getattr(ds, "Modality", "")),
                "study_description": str(getattr(ds, "StudyDescription", "")),
                "series_description": str(getattr(ds, "SeriesDescription", "")),
                "institution": str(getattr(ds, "InstitutionName", "")),
            }
            # Extract radiology report text if present (tag 0040,A730)
            report_text = ""
            if hasattr(ds, "ContentSequence"):
                for item in ds.ContentSequence:
                    if hasattr(item, "TextValue"):
                        report_text += item.TextValue + "\n"
            text = report_text or f"[DICOM study: {structured.get('study_description', 'unknown')}]"
        except ImportError:
            structured = {}
            text = f"[DICOM file - install pydicom for extraction]"
        return LoadedDocument(
            document_id=doc_id,
            file_path=file_path,
            content_type="radiology_report",
            text_content=text,
            structured_data=structured,
            metadata={"format": "dicom"},
        )

    def _load_hl7(self, doc_id: str, file_path: str) -> LoadedDocument:
        """Parse HL7 message extracting structured fields."""
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            raw = f.read()
        structured = self._parse_hl7_basic(raw)
        return LoadedDocument(
            document_id=doc_id,
            file_path=file_path,
            content_type="hl7_message",
            text_content=raw,
            structured_data=structured,
            metadata={"format": "hl7"},
            requires_structured_path=True,
        )

    def _load_fhir(self, doc_id: str, file_path: str) -> LoadedDocument:
        """Parse FHIR JSON resource."""
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        resource_type = data.get("resourceType", "unknown")
        text_content = self._fhir_to_text(data)
        return LoadedDocument(
            document_id=doc_id,
            file_path=file_path,
            content_type="fhir_resource",
            text_content=text_content,
            structured_data=data,
            metadata={"format": "fhir", "resource_type": resource_type},
            requires_structured_path=True,
        )

    def _detect_clinical_type(self, text: str) -> str:
        """Heuristic detection of clinical document type."""
        text_lower = text.lower()
        if any(w in text_lower for w in ["discharge summary", "discharge note"]):
            return "discharge_summary"
        if any(w in text_lower for w in ["radiology", "impression:", "findings:", "mri", "ct scan", "x-ray"]):
            return "radiology_report"
        if any(w in text_lower for w in ["lab result", "laboratory", "specimen", "result:"]):
            return "lab_report"
        if any(w in text_lower for w in ["history of present illness", "chief complaint", "assessment and plan"]):
            return "clinical_note"
        return "clinical_note"

    def _parse_hl7_basic(self, raw: str) -> Dict[str, Any]:
        """Basic HL7 v2.x parser extracting common fields."""
        structured: Dict[str, Any] = {}
        for line in raw.splitlines():
            if line.startswith("MSH"):
                parts = line.split("|")
                if len(parts) > 9:
                    structured["message_type"] = parts[8] if len(parts) > 8 else ""
                    structured["patient_id"] = parts[3] if len(parts) > 3 else ""
            elif line.startswith("PID"):
                parts = line.split("|")
                structured["patient_name"] = parts[5] if len(parts) > 5 else ""
                structured["birth_date"] = parts[7] if len(parts) > 7 else ""
            elif line.startswith("OBX"):
                parts = line.split("|")
                if "observations" not in structured:
                    structured["observations"] = []
                obs = {
                    "type": parts[3] if len(parts) > 3 else "",
                    "value": parts[5] if len(parts) > 5 else "",
                    "units": parts[6] if len(parts) > 6 else "",
                }
                structured["observations"].append(obs)
        return structured

    def _fhir_to_text(self, resource: Dict) -> str:
        """Convert a FHIR resource to a human-readable text representation."""
        resource_type = resource.get("resourceType", "Resource")
        lines = [f"FHIR {resource_type}:"]
        if resource_type == "Patient":
            name = resource.get("name", [{}])[0] if resource.get("name") else {}
            given = " ".join(name.get("given", []))
            family = name.get("family", "")
            lines.append(f"Name: {given} {family}".strip())
            lines.append(f"Birth Date: {resource.get('birthDate', 'unknown')}")
        elif resource_type == "MedicationRequest":
            med = resource.get("medicationCodeableConcept", {})
            lines.append(f"Medication: {med.get('text', 'unknown')}")
            dosage = resource.get("dosageInstruction", [{}])[0] if resource.get("dosageInstruction") else {}
            lines.append(f"Dosage: {dosage.get('text', 'unknown')}")
        elif resource_type == "Observation":
            code = resource.get("code", {}).get("text", "unknown")
            value = resource.get("valueQuantity", {})
            lines.append(f"Observation: {code}")
            lines.append(f"Value: {value.get('value', '')} {value.get('unit', '')}")
        elif resource_type == "Condition":
            code = resource.get("code", {}).get("text", "unknown")
            lines.append(f"Condition: {code}")
            lines.append(f"Status: {resource.get('clinicalStatus', {}).get('coding', [{}])[0].get('code', 'unknown')}")
        else:
            lines.append(json.dumps(resource, indent=2)[:500])
        return "\n".join(lines)
