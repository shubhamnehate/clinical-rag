"""FHIR R4 resource parser - extracts structured clinical data."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class FHIRResource:
    resource_id: str
    resource_type: str
    patient_id: Optional[str]
    date: Optional[str]
    fields: Dict[str, Any] = field(default_factory=dict)
    raw: Dict = field(default_factory=dict)


class FHIRParser:
    """Parses FHIR R4 JSON resources into structured data for direct querying."""

    def parse(self, resource: Dict) -> FHIRResource:
        resource_type = resource.get("resourceType", "unknown")
        rid = resource.get("id", "")

        parser = getattr(self, f"_parse_{resource_type.lower()}", self._parse_generic)
        return parser(resource, rid, resource_type)

    def _parse_patient(self, r: Dict, rid: str, rtype: str) -> FHIRResource:
        name = (r.get("name") or [{}])[0]
        given = " ".join(name.get("given", []))
        family = name.get("family", "")
        return FHIRResource(
            resource_id=rid,
            resource_type=rtype,
            patient_id=r.get("id"),
            date=r.get("birthDate"),
            fields={
                "name": f"{given} {family}".strip(),
                "birth_date": r.get("birthDate"),
                "gender": r.get("gender"),
                "active": r.get("active", True),
            },
            raw=r,
        )

    def _parse_medicationrequest(self, r: Dict, rid: str, rtype: str) -> FHIRResource:
        med = r.get("medicationCodeableConcept", {})
        dosage = (r.get("dosageInstruction") or [{}])[0]
        subject = r.get("subject", {}).get("reference", "").replace("Patient/", "")
        return FHIRResource(
            resource_id=rid,
            resource_type=rtype,
            patient_id=subject,
            date=r.get("authoredOn"),
            fields={
                "medication": med.get("text") or (med.get("coding") or [{}])[0].get("display", "unknown"),
                "status": r.get("status"),
                "dosage": dosage.get("text"),
                "route": dosage.get("route", {}).get("text"),
                "frequency": (dosage.get("timing") or {}).get("code", {}).get("text"),
            },
            raw=r,
        )

    def _parse_observation(self, r: Dict, rid: str, rtype: str) -> FHIRResource:
        code = r.get("code", {})
        value_qty = r.get("valueQuantity", {})
        value_str = r.get("valueString", "")
        subject = r.get("subject", {}).get("reference", "").replace("Patient/", "")
        return FHIRResource(
            resource_id=rid,
            resource_type=rtype,
            patient_id=subject,
            date=r.get("effectiveDateTime"),
            fields={
                "name": code.get("text") or (code.get("coding") or [{}])[0].get("display", "unknown"),
                "value": value_qty.get("value", value_str),
                "unit": value_qty.get("unit"),
                "status": r.get("status"),
                "interpretation": (r.get("interpretation") or [{}])[0].get("text"),
            },
            raw=r,
        )

    def _parse_condition(self, r: Dict, rid: str, rtype: str) -> FHIRResource:
        code = r.get("code", {})
        subject = r.get("subject", {}).get("reference", "").replace("Patient/", "")
        clinical_status = (r.get("clinicalStatus") or {}).get("coding", [{}])[0].get("code", "unknown")
        return FHIRResource(
            resource_id=rid,
            resource_type=rtype,
            patient_id=subject,
            date=r.get("onsetDateTime") or r.get("recordedDate"),
            fields={
                "condition": code.get("text") or (code.get("coding") or [{}])[0].get("display", "unknown"),
                "clinical_status": clinical_status,
                "severity": (r.get("severity") or {}).get("text"),
                "icd10": next(
                    (c.get("code") for c in code.get("coding", []) if "icd" in c.get("system", "").lower()),
                    None,
                ),
            },
            raw=r,
        )

    def _parse_generic(self, r: Dict, rid: str, rtype: str) -> FHIRResource:
        subject = r.get("subject", r.get("patient", {}))
        if isinstance(subject, dict):
            patient_id = subject.get("reference", "").replace("Patient/", "")
        else:
            patient_id = None
        return FHIRResource(
            resource_id=rid,
            resource_type=rtype,
            patient_id=patient_id,
            date=r.get("date") or r.get("effectiveDateTime") or r.get("authoredOn"),
            fields={"raw_summary": str(r)[:200]},
            raw=r,
        )
