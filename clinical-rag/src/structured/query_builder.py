"""
Structured query builder for FHIR/HL7 data.
Bypasses vector search for structured queries (critical design requirement).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .fhir_parser import FHIRResource
from .hl7_parser import HL7Message


@dataclass
class StructuredQueryResult:
    query: str
    resource_type: str
    results: List[Dict[str, Any]]
    total_count: int
    answer_text: str  # Human-readable summary


class StructuredQueryBuilder:
    """
    Builds and executes structured queries against FHIR/HL7 data.
    Does NOT use vector search - operates directly on parsed structured data.
    """

    def __init__(self):
        self._fhir_store: List[FHIRResource] = []
        self._hl7_store: List[HL7Message] = []

    def add_fhir_resource(self, resource: FHIRResource) -> None:
        self._fhir_store.append(resource)

    def add_hl7_message(self, message: HL7Message) -> None:
        self._hl7_store.append(message)

    def query(
        self,
        natural_language_query: str,
        patient_id: Optional[str] = None,
    ) -> StructuredQueryResult:
        """Parse natural language and execute structured query."""
        query_lower = natural_language_query.lower()

        # Determine what resource type to query
        if any(w in query_lower for w in ["medication", "drug", "prescription", "rx"]):
            return self._query_medications(natural_language_query, patient_id)
        elif any(w in query_lower for w in ["lab", "result", "test", "observation", "vital"]):
            return self._query_observations(natural_language_query, patient_id)
        elif any(w in query_lower for w in ["condition", "diagnosis", "diagnos", "problem"]):
            return self._query_conditions(natural_language_query, patient_id)
        else:
            return self._query_all(natural_language_query, patient_id)

    def _query_medications(self, query: str, patient_id: Optional[str]) -> StructuredQueryResult:
        resources = [
            r for r in self._fhir_store
            if r.resource_type in ("MedicationRequest", "MedicationAdministration")
        ]
        if patient_id:
            resources = [r for r in resources if r.patient_id == patient_id]

        results = [r.fields for r in resources]
        if results:
            meds = [r.get("medication", "unknown") for r in results]
            answer = f"Found {len(results)} medication(s): {', '.join(meds)}"
        else:
            answer = "No medication records found for this patient."

        return StructuredQueryResult(
            query=query,
            resource_type="MedicationRequest",
            results=results,
            total_count=len(results),
            answer_text=answer,
        )

    def _query_observations(self, query: str, patient_id: Optional[str]) -> StructuredQueryResult:
        resources = [r for r in self._fhir_store if r.resource_type == "Observation"]
        if patient_id:
            resources = [r for r in resources if r.patient_id == patient_id]

        # Also check HL7 observations
        hl7_obs = []
        for msg in self._hl7_store:
            if not patient_id or msg.patient_id == patient_id:
                hl7_obs.extend(msg.observations)

        results = [r.fields for r in resources] + hl7_obs
        if results:
            obs_names = [r.get("name", r.get("type", "unknown")) for r in results[:5]]
            answer = f"Found {len(results)} observation(s): {', '.join(obs_names)}"
        else:
            answer = "No lab/observation records found for this patient."

        return StructuredQueryResult(
            query=query,
            resource_type="Observation",
            results=results,
            total_count=len(results),
            answer_text=answer,
        )

    def _query_conditions(self, query: str, patient_id: Optional[str]) -> StructuredQueryResult:
        resources = [r for r in self._fhir_store if r.resource_type == "Condition"]
        if patient_id:
            resources = [r for r in resources if r.patient_id == patient_id]

        results = [r.fields for r in resources]
        if results:
            conditions = [r.get("condition", "unknown") for r in results]
            answer = f"Found {len(results)} condition(s): {', '.join(conditions)}"
        else:
            answer = "No condition/diagnosis records found for this patient."

        return StructuredQueryResult(
            query=query,
            resource_type="Condition",
            results=results,
            total_count=len(results),
            answer_text=answer,
        )

    def _query_all(self, query: str, patient_id: Optional[str]) -> StructuredQueryResult:
        resources = self._fhir_store
        if patient_id:
            resources = [r for r in resources if r.patient_id == patient_id]
        results = [r.fields for r in resources[:10]]
        answer = f"Found {len(results)} structured records."
        return StructuredQueryResult(
            query=query,
            resource_type="all",
            results=results,
            total_count=len(results),
            answer_text=answer,
        )
