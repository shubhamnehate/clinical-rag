"""
Output validation with Layer 3 PII scan (CRITICAL).
Scans generated answer BEFORE returning to user.
This is the last line of defense against PII leakage.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from ..ingestion.pii_detection import PIIDetector


@dataclass
class ValidationResult:
    is_valid: bool
    answer: str  # Possibly sanitized
    pii_detected: bool
    pii_types_found: List[str] = field(default_factory=list)
    blocked: bool = False
    block_reason: Optional[str] = None
    warnings: List[str] = field(default_factory=list)


class OutputValidator:
    """
    Layer 3 PII protection: scans LLM output before returning to user.

    CRITICAL: This MUST run before every response to the user.
    Zero tolerance for PII leakage in healthcare context.
    """

    def __init__(self, pii_detector: Optional[PIIDetector] = None, block_on_pii: bool = True):
        self.pii_detector = pii_detector or PIIDetector()
        self.block_on_pii = block_on_pii

    def validate(self, answer: str) -> ValidationResult:
        """
        Validate LLM output. Scans for PII and either blocks or sanitizes.
        """
        # Layer 3 PII scan
        pii_detected, pii_types = self.pii_detector.scan_output(answer)

        if pii_detected:
            if self.block_on_pii:
                return ValidationResult(
                    is_valid=False,
                    answer="[RESPONSE BLOCKED: PII detected in generated output. Please rephrase your query without requesting personally identifiable information.]",
                    pii_detected=True,
                    pii_types_found=pii_types,
                    blocked=True,
                    block_reason=f"PII types detected: {', '.join(pii_types)}",
                )
            else:
                # Sanitize instead of block
                result = self.pii_detector.process("output_validation", answer)
                return ValidationResult(
                    is_valid=True,
                    answer=result.pseudonymized_content,
                    pii_detected=True,
                    pii_types_found=pii_types,
                    warnings=[f"PII was sanitized from output: {', '.join(pii_types)}"],
                )

        # Check for error responses
        if answer.startswith("[LLM Error"):
            return ValidationResult(
                is_valid=False,
                answer="An error occurred generating the response. Please try again.",
                pii_detected=False,
                warnings=["LLM generation error"],
            )

        return ValidationResult(
            is_valid=True,
            answer=answer,
            pii_detected=False,
        )
