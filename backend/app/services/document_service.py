"""
File: app/services/document_service.py
Purpose: Pleading text handling for the Case Knowledge Base (§12) — extract text from an uploaded
    PDF and split it into overlapping chunks for embedding. Both are pure/offline (no network), so
    they are unit-tested directly.
Depends on: pypdf, io, re (stdlib)
Related: app/services/case_knowledge_service.py
Security notes: Operates on pleading bytes/text (attorney work product) in memory only — never
    logged.
"""

from __future__ import annotations

import io
import re

# Chunk sizing in characters (~4 chars/token → ~800-token windows) with overlap so a fact split
# across a boundary is still retrievable from at least one chunk.
CHUNK_CHARS = 3200
CHUNK_OVERLAP = 400

# Below this many extracted characters a PDF is treated as having no usable text (empty OR
# near-empty — e.g. a scanned/image PDF where pypdf recovers only a few header/watermark chars).
# Deliberately low so a legitimately short document is never false-failed; any real rule/pleading
# has far more text than this.
MIN_EXTRACTED_CHARS = 20


def extract_pdf_text(data: bytes) -> str:
    """Extract text from a PDF's bytes. Empty string if it has no extractable text (scanned/image
    PDFs need OCR — a documented follow-up, §12)."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pages = [(page.extract_text() or "") for page in reader.pages]
    return _normalize("\n\n".join(pages))


def _normalize(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_text(
    text: str, size: int = CHUNK_CHARS, overlap: int = CHUNK_OVERLAP
) -> list[str]:
    """Split text into overlapping windows, preferring to break at paragraph/sentence boundaries.
    Pure and deterministic."""
    cleaned = _normalize(text)
    if not cleaned:
        return []
    chunks: list[str] = []
    start = 0
    n = len(cleaned)
    while start < n:
        end = min(start + size, n)
        if end < n:
            # back off to the last paragraph/sentence break in the window for a cleaner cut
            window = cleaned[start:end]
            for sep in ("\n\n", ". ", "\n", " "):
                cut = window.rfind(sep)
                if cut > size // 2:
                    end = start + cut + len(sep)
                    break
        chunk = cleaned[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return chunks
