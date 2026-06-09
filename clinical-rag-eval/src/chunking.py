"""
Chunking Module — Clinical RAG Prototype
=========================================
Design decisions documented inline.

Strategy: Section-Aware Hybrid Chunking
  1. Split on clinical section headers (CHIEF COMPLAINT, MEDICATIONS, etc.)
  2. Within each section use paragraph splitting
  3. Fall back to sliding window for long paragraphs
  4. Preserve section metadata per chunk for downstream filtering

Why NOT fixed-size chunking for clinical text:
  - Fixed-size splits mid-sentence break semantic coherence
    e.g. "Aspirin 81mg [split] daily — post-PCI" loses clinical meaning
  - Clinical notes have natural semantic units (sections)
  - Sections like MEDICATIONS should stay coherent for drug queries

Why NOT sentence-level chunking alone:
  - Clinical abbreviations confuse sentence splitters (Dr., vs., i.v.)
  - Loses intra-section context (e.g. lab values + interpretation belong together)

Overlap strategy: 50-token overlap between chunks
  - Preserves context across section boundaries
  - Prevents answers from falling in split gaps
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# ── Regex for clinical section headers ──────────────────────────────────────
SECTION_RE = re.compile(
    r"^(?:CHIEF COMPLAINT|HISTORY OF PRESENT ILLNESS|HPI|PAST MEDICAL HISTORY|"
    r"MEDICATIONS?(?: ON ADMISSION| AT DISCHARGE)?|ALLERGIES|"
    r"PHYSICAL EXAMINATION(?: ON ADMISSION)?|VITAL SIGNS?|"
    r"INVESTIGATIONS?|LABORATORY|LAB(ORATORY)? RESULTS?|HAEMATOLOGY|BIOCHEMISTRY|"
    r"COAGULATION|HOSPITAL COURSE|ASSESSMENT AND PLAN|ASSESSMENT|PLAN|"
    r"DISCHARGE CONDITION|DISCHARGE MEDICATIONS?|FOLLOW.UP(?: PLAN)?|"
    r"DIAGNOS[EI]S|FINDINGS|IMPRESSION|RECOMMENDATION|"
    r"SUBJECTIVE|OBJECTIVE|NOTES?|EDUCATION TODAY)[:\s]*$",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass
class Chunk:
    """A semantically coherent unit of clinical text."""
    chunk_id: str
    doc_id: str
    text: str
    section: str          # Clinical section label (e.g. "MEDICATIONS AT DISCHARGE")
    char_start: int       # Character offset in source document
    token_count: int      # Approximate token count (~4 chars/token)
    overlap_prev: bool = False
    patient_id: Optional[str] = None
    doc_type: Optional[str] = None

    @property
    def preview(self) -> str:
        return self.text[:120].replace("\n", " ") + ("..." if len(self.text) > 120 else "")


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def chunk_document(
    doc_id: str,
    text: str,
    patient_id: Optional[str] = None,
    doc_type: Optional[str] = None,
    target_tokens: int = 300,
    max_tokens: int = 600,
    min_tokens: int = 15,
    overlap_tokens: int = 50,
) -> List[Chunk]:
    """
    Chunk a clinical document using section-aware hybrid strategy.

    Parameters
    ----------
    target_tokens : Ideal chunk size (~300 tokens ≈ 1200 chars)
    max_tokens    : Hard ceiling before splitting (~600 tokens ≈ 2400 chars)
    min_tokens    : Discard chunks below this size (noise)
    overlap_tokens: Tokens to repeat between adjacent chunks
    """
    sections = _split_sections(text)
    chunks: List[Chunk] = []
    idx = 0

    for section_name, section_text, char_offset in sections:
        section_chunks = _chunk_section(
            section_text, target_tokens, max_tokens, overlap_tokens
        )
        prev_text: Optional[str] = None
        for piece_text in section_chunks:
            tok = _estimate_tokens(piece_text)
            if tok < min_tokens:
                prev_text = piece_text
                continue
            # Add overlap from previous chunk
            if prev_text and overlap_tokens > 0:
                overlap_words = prev_text.split()[-overlap_tokens:]
                piece_text = " ".join(overlap_words) + "\n" + piece_text
                tok = _estimate_tokens(piece_text)
            chunks.append(Chunk(
                chunk_id=f"{doc_id}_{idx}",
                doc_id=doc_id,
                text=piece_text.strip(),
                section=section_name,
                char_start=char_offset,
                token_count=tok,
                overlap_prev=(prev_text is not None),
                patient_id=patient_id,
                doc_type=doc_type,
            ))
            prev_text = piece_text
            idx += 1

    return chunks


def _split_sections(text: str) -> List[Tuple[str, str, int]]:
    """Return list of (section_name, section_text, char_offset)."""
    results: List[Tuple[str, str, int]] = []
    current_section = "HEADER"
    current_lines: List[str] = []
    current_offset = 0
    pos = 0

    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if SECTION_RE.match(stripped):
            # Flush current section
            body = "".join(current_lines).strip()
            if body:
                results.append((current_section, body, current_offset))
            current_section = stripped.rstrip(":").upper().strip()
            current_lines = []
            current_offset = pos
        else:
            current_lines.append(line)
        pos += len(line)

    # Flush final section
    body = "".join(current_lines).strip()
    if body:
        results.append((current_section, body, current_offset))

    return results if results else [("DOCUMENT", text, 0)]


def _chunk_section(
    text: str,
    target: int,
    max_t: int,
    overlap: int,
) -> List[str]:
    """Split a section into chunks, respecting paragraph boundaries."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs:
        return []

    chunks: List[str] = []
    current: List[str] = []
    current_tok = 0

    for para in paragraphs:
        tok = _estimate_tokens(para)
        if tok > max_t:
            # Para itself is too big — sliding window
            if current:
                chunks.append("\n\n".join(current))
                current, current_tok = [], 0
            chunks.extend(_sliding_window(para, target, overlap))
            continue

        if current_tok + tok > max_t and current:
            chunks.append("\n\n".join(current))
            # Keep last paragraph as overlap seed
            current = [current[-1], para] if current else [para]
            current_tok = sum(_estimate_tokens(p) for p in current)
        else:
            current.append(para)
            current_tok += tok

    if current:
        chunks.append("\n\n".join(current))
    return chunks


def _sliding_window(text: str, target: int, overlap: int) -> List[str]:
    """Sliding window for oversized paragraphs."""
    words = text.split()
    step = max(1, target - overlap)
    result: List[str] = []
    i = 0
    while i < len(words):
        result.append(" ".join(words[i : i + target]))
        if i + target >= len(words):
            break
        i += step
    return result


def print_chunk_stats(chunks: List[Chunk]) -> None:
    """Print a summary table of chunks for inspection."""
    print(f"\n{'='*70}")
    print(f"  CHUNKS: {len(chunks)} total")
    print(f"{'='*70}")
    print(f"  {'#':<4} {'Section':<35} {'Tokens':<8} {'Preview'}")
    print(f"  {'-'*4} {'-'*35} {'-'*8} {'-'*30}")
    for i, c in enumerate(chunks):
        print(f"  {i:<4} {c.section[:35]:<35} {c.token_count:<8} {c.preview[:50]}")
    avg = sum(c.token_count for c in chunks) / max(len(chunks), 1)
    print(f"\n  Average tokens/chunk: {avg:.0f}")
    sections = {c.section for c in chunks}
    print(f"  Distinct sections: {len(sections)}")
    print(f"{'='*70}\n")
