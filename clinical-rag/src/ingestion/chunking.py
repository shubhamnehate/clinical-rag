"""
Hybrid chunking strategy for clinical documents.
Section-aware + paragraph-based + sliding window with overlap.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

# Common clinical note section headers
_SECTION_HEADERS = re.compile(
    r"^(?:CHIEF COMPLAINT|HISTORY OF PRESENT ILLNESS|HPI|PAST MEDICAL HISTORY|PMH|"
    r"MEDICATIONS|ALLERGIES|PHYSICAL EXAMINATION|REVIEW OF SYSTEMS|ROS|"
    r"ASSESSMENT AND PLAN|ASSESSMENT|PLAN|LAB RESULTS|LABORATORY|IMAGING|"
    r"DISCHARGE SUMMARY|DISCHARGE MEDICATIONS|FOLLOW.UP|SOCIAL HISTORY|"
    r"FAMILY HISTORY|VITAL SIGNS|IMPRESSION|FINDINGS)[:\s]*$",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass
class DocumentChunk:
    chunk_id: str
    parent_doc_id: str
    chunk_index: int
    text: str
    section: Optional[str] = None
    token_count: int = 0
    overlap_prev: bool = False
    overlap_next: bool = False
    patient_id: Optional[str] = None
    document_date: Optional[str] = None
    document_type: Optional[str] = None
    version: int = 1
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.token_count == 0:
            self.token_count = _estimate_tokens(self.text)


def _estimate_tokens(text: str) -> int:
    """Simple token estimation: ~4 chars per token."""
    return max(1, len(text) // 4)


class ChunkingEngine:
    """
    Hybrid chunking: section-aware splitting + paragraph chunking + sliding window.
    """

    def __init__(
        self,
        target_size_tokens: int = 400,
        max_size_tokens: int = 800,
        min_size_tokens: int = 20,
        overlap_tokens: int = 50,
        preserve_sections: bool = True,
    ):
        self.target_size = target_size_tokens
        self.max_size = max_size_tokens
        self.min_size = min_size_tokens
        self.overlap = overlap_tokens
        self.preserve_sections = preserve_sections

    def chunk(
        self,
        doc_id: str,
        text: str,
        patient_id: Optional[str] = None,
        document_date: Optional[str] = None,
        document_type: Optional[str] = None,
        version: int = 1,
    ) -> List[DocumentChunk]:
        """Chunk a document into semantically meaningful pieces."""
        if not text.strip():
            return []

        if self.preserve_sections:
            sections = self._split_into_sections(text)
        else:
            sections = [("DOCUMENT", text)]

        chunks: List[DocumentChunk] = []
        chunk_idx = 0

        for section_name, section_text in sections:
            section_chunks = self._chunk_section(section_text)
            for i, chunk_text in enumerate(section_chunks):
                token_count = _estimate_tokens(chunk_text)
                if token_count < self.min_size:
                    continue
                chunks.append(DocumentChunk(
                    chunk_id=f"{doc_id}_chunk_{chunk_idx}",
                    parent_doc_id=doc_id,
                    chunk_index=chunk_idx,
                    text=chunk_text,
                    section=section_name,
                    token_count=token_count,
                    overlap_prev=(i > 0),
                    overlap_next=(i < len(section_chunks) - 1),
                    patient_id=patient_id,
                    document_date=document_date,
                    document_type=document_type,
                    version=version,
                ))
                chunk_idx += 1

        # Mark overlap flags
        for i in range(1, len(chunks)):
            chunks[i].overlap_prev = True
        for i in range(len(chunks) - 1):
            chunks[i].overlap_next = True

        return chunks

    def _split_into_sections(self, text: str) -> List[tuple]:
        """Split text into (section_name, section_text) pairs."""
        sections = []
        current_section = "PREAMBLE"
        current_lines: List[str] = []

        for line in text.splitlines(keepends=True):
            m = _SECTION_HEADERS.match(line.strip())
            if m:
                if current_lines:
                    section_text = "".join(current_lines).strip()
                    if section_text:
                        sections.append((current_section, section_text))
                current_section = line.strip().rstrip(":").upper()
                current_lines = [line]
            else:
                current_lines.append(line)

        if current_lines:
            section_text = "".join(current_lines).strip()
            if section_text:
                sections.append((current_section, section_text))

        return sections if sections else [("DOCUMENT", text)]

    def _chunk_section(self, text: str) -> List[str]:
        """Chunk a section using paragraph splitting + sliding window."""
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]

        # If only one paragraph, use sliding window
        if len(paragraphs) <= 1:
            return self._sliding_window(text)

        chunks: List[str] = []
        current_chunk: List[str] = []
        current_tokens = 0

        for para in paragraphs:
            para_tokens = _estimate_tokens(para)

            # Paragraph itself exceeds max; split it further
            if para_tokens > self.max_size:
                if current_chunk:
                    chunks.append("\n\n".join(current_chunk))
                    current_chunk = []
                    current_tokens = 0
                chunks.extend(self._sliding_window(para))
                continue

            if current_tokens + para_tokens > self.max_size and current_chunk:
                chunks.append("\n\n".join(current_chunk))
                # Add overlap: keep last paragraph in new chunk
                overlap_para = current_chunk[-1] if current_chunk else ""
                current_chunk = [overlap_para, para] if overlap_para else [para]
                current_tokens = _estimate_tokens("\n\n".join(current_chunk))
            else:
                current_chunk.append(para)
                current_tokens += para_tokens

        if current_chunk:
            chunks.append("\n\n".join(current_chunk))

        return chunks

    def _sliding_window(self, text: str) -> List[str]:
        """Split long text using sliding window with overlap."""
        words = text.split()
        target_words = self.target_size * 4  # ~4 chars/token → ~1 word/token approx
        overlap_words = self.overlap * 4

        if len(words) <= target_words:
            return [text]

        chunks = []
        start = 0
        while start < len(words):
            end = min(start + target_words, len(words))
            chunk = " ".join(words[start:end])
            chunks.append(chunk)
            if end >= len(words):
                break
            start = end - overlap_words
        return chunks
