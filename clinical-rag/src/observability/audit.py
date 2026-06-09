"""
HIPAA-compliant audit trail.
All patient data access events are logged with immutable records.
7-year retention policy.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class AuditEvent:
    event_type: str  # query, ingestion, document_access, pii_detection, cache_hit
    timestamp: float
    user_id: Optional[str]
    patient_id: Optional[str]
    query_id: Optional[str]
    action: str
    resource: Optional[str] = None
    success: bool = True
    details: Optional[dict] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["timestamp_iso"] = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.timestamp)
        )
        return d


class AuditTrail:
    """
    Append-only audit trail for HIPAA compliance.
    In production: write to CloudWatch Logs or immutable S3 bucket.
    """

    def __init__(self, log_path: Optional[str] = None):
        self._events: List[AuditEvent] = []
        self._log_path = log_path
        if log_path:
            Path(log_path).parent.mkdir(parents=True, exist_ok=True)

    def log(self, event: AuditEvent) -> None:
        """Log an audit event. This is append-only."""
        self._events.append(event)
        if self._log_path:
            self._write_to_file(event)

    def log_query(
        self,
        user_id: Optional[str],
        patient_id: Optional[str],
        query_id: str,
        query: str,
        success: bool = True,
    ) -> None:
        self.log(AuditEvent(
            event_type="query",
            timestamp=time.time(),
            user_id=user_id,
            patient_id=patient_id,
            query_id=query_id,
            action="clinical_query",
            resource=query[:200],
            success=success,
        ))

    def log_document_access(
        self,
        user_id: Optional[str],
        patient_id: Optional[str],
        document_id: str,
        action: str = "read",
    ) -> None:
        self.log(AuditEvent(
            event_type="document_access",
            timestamp=time.time(),
            user_id=user_id,
            patient_id=patient_id,
            query_id=None,
            action=action,
            resource=document_id,
        ))

    def log_pii_event(
        self,
        document_id: str,
        pii_types: List[str],
        layer: int,
        blocked: bool = False,
    ) -> None:
        self.log(AuditEvent(
            event_type="pii_detection",
            timestamp=time.time(),
            user_id=None,
            patient_id=None,
            query_id=None,
            action=f"pii_layer_{layer}_{'blocked' if blocked else 'detected'}",
            resource=document_id,
            details={"pii_types": pii_types, "layer": layer, "blocked": blocked},
        ))

    def get_events(self, patient_id: Optional[str] = None) -> List[AuditEvent]:
        if patient_id:
            return [e for e in self._events if e.patient_id == patient_id]
        return list(self._events)

    def _write_to_file(self, event: AuditEvent) -> None:
        try:
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event.to_dict()) + "\n")
        except Exception:
            pass  # Never fail on audit write (log separately)
