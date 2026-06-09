"""HL7 v2.x message parser."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class HL7Message:
    message_type: str
    patient_id: Optional[str]
    patient_name: Optional[str]
    date: Optional[str]
    segments: Dict[str, List[str]] = field(default_factory=dict)
    observations: List[Dict[str, str]] = field(default_factory=list)
    medications: List[Dict[str, str]] = field(default_factory=list)


class HL7Parser:
    """Parses HL7 v2.x messages into structured data."""

    def parse(self, raw_message: str) -> HL7Message:
        segments = self._split_segments(raw_message)

        msg_type = ""
        patient_id = None
        patient_name = None
        date = None
        observations = []
        medications = []

        for seg_id, fields in segments.items():
            if seg_id == "MSH":
                msg_type = fields[8] if len(fields) > 8 else ""
                date = fields[6] if len(fields) > 6 else ""
            elif seg_id == "PID":
                patient_id = fields[3] if len(fields) > 3 else None
                patient_name = fields[5] if len(fields) > 5 else None
            elif seg_id == "OBX":
                obs = {
                    "set_id": fields[1] if len(fields) > 1 else "",
                    "type": fields[3] if len(fields) > 3 else "",
                    "value": fields[5] if len(fields) > 5 else "",
                    "units": fields[6] if len(fields) > 6 else "",
                    "reference_range": fields[7] if len(fields) > 7 else "",
                    "abnormal_flag": fields[8] if len(fields) > 8 else "",
                    "status": fields[11] if len(fields) > 11 else "",
                }
                observations.append(obs)
            elif seg_id == "RXA":
                med = {
                    "medication": fields[5] if len(fields) > 5 else "",
                    "dose": fields[6] if len(fields) > 6 else "",
                    "units": fields[7] if len(fields) > 7 else "",
                    "route": fields[12] if len(fields) > 12 else "",
                }
                medications.append(med)

        return HL7Message(
            message_type=msg_type,
            patient_id=patient_id,
            patient_name=patient_name,
            date=date,
            segments=segments,
            observations=observations,
            medications=medications,
        )

    def _split_segments(self, raw: str) -> Dict[str, List[str]]:
        """Split HL7 message into segments and fields."""
        segments: Dict[str, List[str]] = {}
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            fields = line.split("|")
            seg_id = fields[0]
            segments[seg_id] = fields
        return segments
