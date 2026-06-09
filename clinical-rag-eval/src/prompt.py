"""
Prompt Construction Module — Clinical RAG Prototype
====================================================
Two key principles implemented here:

1. PSEUDONYMISATION (before any text enters the prompt)
   ─────────────────────────────────────────────────────
   Clinical notes contain PII that must not reach the LLM in raw form.
   We apply pseudonymisation at TWO layers here:
     • Layer 1 (ingestion): PII replaced before chunk storage
     • Layer 2 (prompt):    Residual-check on assembled context

   Pattern coverage:
     SSN (###-##-####), phone, email, MRN, dates of birth,
     specific dates (retain year only), provider names in context,
     patient names in context, device serial numbers.

   Method: SHA-256 keyed hashing (HMAC-style) with a salt.
   Same original → same pseudonym (consistent across documents).
   One-way: pseudonym cannot be reversed without salt.

2. MINIMUM CONTEXT WINDOW
   ─────────────────────────────────────────────────────────────────
   We assemble only as much context as needed, ranked by relevance.
   Budget = model_max_tokens - response_reserved - query_tokens
   Chunks are added in rank order until budget is exhausted.

   Why minimum context?
   • Reduces hallucination risk (LLM confused by irrelevant context)
   • Reduces latency (fewer input tokens = faster generation)
   • Reduces cost
   • Forces explainability: we know EXACTLY what the LLM saw

   Token estimate: len(text) // 4  (rough but consistent)
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .retrieval import RetrievalResult


# ── PII patterns ──────────────────────────────────────────────────────────────
_PII_PATTERNS = [
    ("ssn",          re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("phone",        re.compile(r"\(?\d{3}\)?[\s\-\.]\d{3}[\s\-\.]\d{4}\b")),
    ("email",        re.compile(r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b")),
    ("mrn",          re.compile(r"\bMRN[:\s]+\d{5,10}\b", re.I)),
    ("dob",          re.compile(r"\b(?:DOB|Date of Birth)[:\s]+\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}\b", re.I)),
    ("spec_date",    re.compile(r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
                                r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
                                r"Dec(?:ember)?)\s+\d{1,2},?\s+\d{4}\b", re.I)),
    ("date_num",     re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b")),
    ("age_over_89",  re.compile(r"\b(?:9\d|1[01]\d)\s*(?:year|yr)s?\s*old\b", re.I)),
    ("device_id",    re.compile(r"\bSerial\s*(?:No|#)[:\s]+[A-Z0-9\-]{6,20}\b", re.I)),
    ("name_context", re.compile(r"\b(?:Dr\.|Patient|Pt\.?)[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})", re.M)),
]


class Pseudonymiser:
    """
    Consistent, one-way pseudonymisation using SHA-256 hashing.

    Usage:
        p = Pseudonymiser(salt="secret")
        clean_text = p.clean(raw_text)
        detected  = p.scan(text)  # returns True if PII found
    """

    def __init__(self, salt: str = "clinical_rag_salt"):
        self._salt = salt
        self._cache: dict = {}           # original → pseudonym (session-level)

    def clean(self, text: str) -> Tuple[str, List[dict]]:
        """
        Replace PII in text with pseudonyms.
        Returns (cleaned_text, list_of_detections).
        """
        entities = []
        result = text

        for ptype, pattern in _PII_PATTERNS:
            for m in pattern.finditer(result):
                orig = m.group()
                pseudo = self._pseudonym(ptype, orig)
                entities.append({"type": ptype, "pseudonym": pseudo})
                result = result.replace(orig, pseudo, 1)

        return result, entities

    def scan(self, text: str) -> Tuple[bool, List[str]]:
        """Scan for PII without replacing. Returns (found, types)."""
        found_types = []
        for ptype, pattern in _PII_PATTERNS:
            if pattern.search(text):
                found_types.append(ptype)
        return bool(found_types), found_types

    def _pseudonym(self, ptype: str, original: str) -> str:
        key = f"{self._salt}:{ptype}:{original}"
        if key not in self._cache:
            h = hashlib.sha256(key.encode()).hexdigest()[:8]
            labels = {
                "ssn": "[SSN_REDACTED]",
                "phone": "[PHONE_REDACTED]",
                "email": "[EMAIL_REDACTED]",
                "mrn": f"[MRN_{h}]",
                "dob": "[DOB_REDACTED]",
                "spec_date": "[DATE_REDACTED]",
                "date_num": "[DATE_REDACTED]",
                "age_over_89": "[AGE>89]",
                "device_id": f"[DEVICE_{h}]",
                "name_context": f"[PERSON_{h}]",
            }
            self._cache[key] = labels.get(ptype, f"[{ptype.upper()}_{h}]")
        return self._cache[key]


# ── Prompt builder ────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a clinical decision-support assistant. Answer questions about patient
records using ONLY the provided context. Do not use external knowledge.

Rules:
- If the answer is not in the context, say: "Not found in the provided records."
- Cite the source section for each fact (e.g. "[DISCHARGE MEDICATIONS]").
- Use concise, professional medical language.
- Never reproduce or infer patient identifiers."""


@dataclass
class BuiltPrompt:
    system: str
    user: str
    context_chunks_used: int
    context_tokens: int
    budget_tokens: int
    pii_guard_triggered: bool
    pii_types_found: List[str] = field(default_factory=list)
    token_utilisation: float = 0.0

    def display(self) -> None:
        print("\n" + "═" * 70)
        print("  CONSTRUCTED PROMPT")
        print("═" * 70)
        print(f"  Context chunks used : {self.context_chunks_used}")
        print(f"  Context tokens      : {self.context_tokens:,}  (budget: {self.budget_tokens:,})")
        print(f"  Token utilisation   : {self.token_utilisation:.0%}")
        print(f"  PII guard triggered : {self.pii_guard_triggered}"
              + (f" — types: {self.pii_types_found}" if self.pii_types_found else ""))
        print("─" * 70)
        print("  SYSTEM:")
        print(f"  {self.system[:200]}...")
        print("─" * 70)
        print("  USER (first 600 chars):")
        print(self.user[:600])
        print("═" * 70 + "\n")


class PromptBuilder:
    """
    Assembles the minimum context needed to answer a query.

    Design:
      1. Pseudonymise each retrieved chunk (Layer 2 guard)
      2. Add chunks in rank order until token budget exhausted
      3. Format with source citations for traceability
    """

    def __init__(
        self,
        pseudonymiser: Optional[Pseudonymiser] = None,
        model_max_tokens: int = 8192,
        response_reserved: int = 512,
        query_overhead: int = 256,
    ):
        self.ps = pseudonymiser or Pseudonymiser()
        # Minimum context budget
        self.budget = model_max_tokens - response_reserved - query_overhead

    def build(
        self,
        query: str,
        results: List[RetrievalResult],
    ) -> BuiltPrompt:
        """
        Build prompt with minimum context.

        Token budget = model_max - response_reserved - query_overhead
        Chunks added in rank order until budget exhausted.
        """
        context_parts: List[str] = []
        total_tokens = 0
        pii_triggered = False
        pii_types: List[str] = []

        for r in results:
            chunk_text = r.chunk.text
            # Layer 2: pseudonymise residual PII in context
            clean_text, detections = self.ps.clean(chunk_text)
            if detections:
                pii_triggered = True
                pii_types.extend(d["type"] for d in detections)

            chunk_tokens = len(clean_text) // 4
            if total_tokens + chunk_tokens > self.budget:
                break  # Minimum context: stop at budget

            source_label = (
                f"[Source: {r.chunk.doc_type or 'record'} | "
                f"Section: {r.chunk.section} | "
                f"RRF score: {r.rrf_score:.4f}"
                + (f" | Rerank: {r.rerank_score:.3f}" if r.rerank_score else "")
                + "]"
            )
            context_parts.append(f"{source_label}\n{clean_text}")
            total_tokens += chunk_tokens

        context_str = "\n\n---\n\n".join(context_parts) if context_parts else "No relevant context retrieved."

        user_message = (
            f"CLINICAL RECORDS CONTEXT:\n\n"
            f"{context_str}\n\n"
            f"---\n\n"
            f"QUESTION: {query}\n\n"
            f"Answer based solely on the context above. Cite source sections."
        )

        return BuiltPrompt(
            system=_SYSTEM_PROMPT,
            user=user_message,
            context_chunks_used=len(context_parts),
            context_tokens=total_tokens,
            budget_tokens=self.budget,
            pii_guard_triggered=pii_triggered,
            pii_types_found=list(set(pii_types)),
            token_utilisation=total_tokens / max(self.budget, 1),
        )
