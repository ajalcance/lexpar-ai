"""
File: app/services/upload_service.py
Purpose: One hardened validator for every PDF upload (case pleadings + court rule documents). The
    guardrails, in order: (1) PDF content-type; (2) a STREAMED size cap — the file is read in
    chunks and rejected the instant it crosses max_upload_mb, so an oversized upload never gets
    fully buffered into memory (the old `await file.read()` loaded the whole thing first, then
    checked the size — a memory-exhaustion vector); (3) non-empty; (4) a real `%PDF-` magic header,
    so a non-PDF renamed/relabelled as a PDF is rejected here, not just guessed at ingest.
Depends on: fastapi (UploadFile/HTTPException), app/config.py
Related: app/api/cases.py, app/api/courts.py (the upload routes), infra/Caddyfile (edge body cap)
Security notes: Operates on uploaded bytes only; never logs file contents. The edge (Caddy
    request_body max_size) is the first line of defense; this is the application-layer backstop.
"""

from fastapi import HTTPException, UploadFile, status

from app.config import get_settings

_PDF_MAGIC = b"%PDF-"
_CHUNK = 1024 * 1024  # 1 MB read granularity for the streamed size cap
_ALLOWED_CONTENT_TYPES = ("application/pdf", "application/octet-stream")


async def read_pdf_upload(file: UploadFile) -> bytes:
    """Validate and return the bytes of a PDF upload, enforcing all four guardrails above. Raises
    HTTPException (415 wrong type / not a PDF, 413 too large, 422 empty) — the routes surface it."""
    if file.content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only PDF files are supported.",
        )

    max_mb = get_settings().max_upload_mb
    max_bytes = max_mb * 1024 * 1024
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(_CHUNK):
        total += len(chunk)
        if total > max_bytes:
            # Stop reading immediately — never buffer beyond the cap.
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File exceeds the {max_mb} MB limit.",
            )
        chunks.append(chunk)

    data = b"".join(chunks)
    if not data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The uploaded file is empty.",
        )
    # A real PDF header appears at (or very near) the start; check the first block, tolerant of a
    # leading BOM/whitespace some exporters emit.
    if _PDF_MAGIC not in data[:1024]:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="The file is not a valid PDF.",
        )
    return data
