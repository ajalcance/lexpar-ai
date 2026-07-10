"""
File: app/services/case_knowledge_service.py
Purpose: The Case Knowledge Base orchestrator (ARCHITECTURE §12). Ingests an uploaded pleading
    (extract → chunk → embed → persist) and answers retrieval queries (embed the query, cosine-rank
    the case's chunks, return the top passages). Also extracts a structured case summary (one LLM
    pass) that the agents keep in context. The embedder and the summarizer are injectable, so ingest
    and retrieval are unit-tested with deterministic fakes and no network.
Depends on: sqlalchemy; app/models/*, app/services/{document,embedding,storage}_service.py
Related: app/api/cases.py (upload + status), app/api/internal.py (agent retrieval),
    agents/case_knowledge.py
Security notes: Handles pleading text (attorney work product) — persisted, never logged. Ingestion
    failures are recorded on the document row (status='failed', error), not swallowed.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DbSession

from app.models.case import Case
from app.models.case_document import CaseChunk, CaseDocument
from app.services import document_service, embedding_service

logger = logging.getLogger("lexpar.knowledge")

DEFAULT_TOP_K = 5

_SUMMARY_SYSTEM = (
    "You are a litigation analyst. Read the pleading excerpt and produce a tight structured brief "
    "the courtroom AI will keep in context. Cover, with short bullet lines: PARTIES; CLAIMS/CAUSES "
    "OF ACTION; KEY DATES; KEY FACTS ALLEGED; DISPUTED FACTS; STIPULATIONS/ADMISSIONS (if any). "
    "Be faithful to the text — do not invent. Plain text, no preamble."
)


def _default_summarizer(text: str) -> str:
    """Live structured-summary pass over the pleading (Fireworks). Injected in tests."""
    from openai import OpenAI

    from app.config import get_settings

    settings = get_settings()
    client = OpenAI(base_url=settings.embedding_endpoint.replace("/embeddings", ""),
                    api_key=settings.fireworks_api_key)
    excerpt = text[:24000]  # bound the prompt; the summary is a digest, not a full re-read
    resp = client.chat.completions.create(
        model=settings.case_summary_model,
        messages=[
            {"role": "system", "content": _SUMMARY_SYSTEM},
            {"role": "user", "content": f"PLEADING:\n{excerpt}"},
        ],
        temperature=0.2,
        max_tokens=1536,
    )
    return (resp.choices[0].message.content or "").strip()


def ingest_document(
    db: DbSession,
    document: CaseDocument,
    raw_bytes: bytes,
    *,
    embedder=embedding_service.embed_texts,
    summarizer=_default_summarizer,
) -> None:
    """Extract → chunk → embed → persist chunks, and refresh the case summary. Sets the document
    status to 'ready' or 'failed' (with the error) — never leaves it silently 'pending'."""
    try:
        text = document_service.extract_pdf_text(raw_bytes)
        chunks = document_service.chunk_text(text)
        if not chunks:
            raise ValueError(
                "no extractable text (a scanned/image PDF needs OCR — see §12 follow-ups)"
            )
        vectors = embedder(chunks)
        if len(vectors) != len(chunks):
            raise ValueError("embedding count did not match chunk count")

        # Replace any prior chunks for this document (idempotent re-ingest).
        db.execute(delete(CaseChunk).where(CaseChunk.document_id == document.id))
        for index, (content, embedding) in enumerate(zip(chunks, vectors)):
            db.add(
                CaseChunk(
                    case_id=document.case_id,
                    document_id=document.id,
                    chunk_index=index,
                    content=content,
                    embedding=list(embedding),
                )
            )
        document.chunk_count = len(chunks)
        document.status = "ready"
        document.error = None

        # Refresh the case summary from the pleading (best-effort — a summary failure must not fail
        # the whole ingest; retrieval still works from the chunks).
        case = db.get(Case, document.case_id)
        if case is not None:
            try:
                case.case_summary = summarizer(text)
            except Exception:
                logger.exception("case summary generation failed for case %s", document.case_id)
        db.commit()
        logger.info("ingested pleading %s (%d chunks)", document.id, len(chunks))
    except Exception as exc:  # noqa: BLE001 — record the failure, don't crash the worker/route
        db.rollback()
        document.status = "failed"
        document.error = str(exc)[:500]
        db.commit()
        logger.exception("ingestion failed for document %s", document.id)


def retrieve(
    db: DbSession,
    case_id: uuid.UUID,
    query: str,
    k: int = DEFAULT_TOP_K,
    *,
    embedder=embedding_service.embed_text,
) -> list[str]:
    """Return the top-k pleading passages most relevant to `query` for a case (cosine over the
    stored chunk embeddings). Empty list if the case has no ingested chunks."""
    rows = db.scalars(select(CaseChunk).where(CaseChunk.case_id == case_id)).all()
    if not rows or not query.strip():
        return []
    query_vec = embedder(query)
    candidates = [(row.content, row.embedding) for row in rows]
    return embedding_service.top_k(query_vec, candidates, k)


def summary_for(db: DbSession, case_id: uuid.UUID) -> str:
    case = db.get(Case, case_id)
    return (case.case_summary or "") if case else ""


def documents_for(db: DbSession, case_id: uuid.UUID) -> list[CaseDocument]:
    return list(
        db.scalars(
            select(CaseDocument).where(
                CaseDocument.case_id == case_id, CaseDocument.deleted_at.is_(None)
            )
        ).all()
    )


def as_status_dict(document: CaseDocument) -> dict:
    return {
        "id": str(document.id),
        "filename": document.filename,
        "status": document.status,
        "chunk_count": document.chunk_count,
        "error": document.error,
    }


# Convenience for the upload route: create the document row, store bytes, kick ingestion.
def create_document_row(
    db: DbSession,
    case_id: uuid.UUID,
    filename: str,
    storage_path: str,
    content_type: str,
    size: int,
) -> CaseDocument:
    document = CaseDocument(
        id=uuid.uuid4(),
        case_id=case_id,
        filename=filename,
        storage_path=storage_path,
        content_type=content_type,
        byte_size=size,
        status="pending",
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


def context_payload(db: DbSession, case_id: uuid.UUID, query: str, k: int = DEFAULT_TOP_K) -> dict:
    """The agent-facing knowledge bundle: the always-in-context summary + the retrieved passages."""
    return {
        "summary": summary_for(db, case_id),
        "passages": retrieve(db, case_id, query, k),
    }
