"""
File: app/services/court_knowledge_service.py
Purpose: The court-rules corpus orchestrator (§13). Ingests an operator-uploaded official rule
    document (extract → chunk → embed → persist CourtRuleChunk rows, with a conservative
    section-heading extraction) and answers retrieval queries (cosine-rank a court's chunks).
    Mirrors case_knowledge_service.py and reuses its already-shared helpers
    (document_service.chunk_text, embedding_service.*) directly — they are standalone pure
    functions, so no refactor was needed to share them (judged: extracting a further "shared
    ingest" abstraction for two callers would be premature).
Depends on: sqlalchemy; app/models/{court_rule}.py,
    app/services/{document,embedding}_service.py
Related: app/api/courts.py (upload + status), agents court retrieval (Phase 3),
    scripts/seed_court.py, docs/ARCHITECTURE.md §13
Security notes: Rule text is public official law (not work product — see models/court_rule.py).
    DELIBERATELY NO LLM summary pass, unlike the case pipeline: only VERBATIM operator-supplied
    text is ever stored or retrieved. A model-written "digest" of the rules would inject
    paraphrased rule content into prompts — exactly what the §13 no-fabrication constraint
    forbids. Ingestion failures are recorded on the document row, never swallowed.
"""

from __future__ import annotations

import logging
import re
import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DbSession

from app.models.court_rule import CourtRuleChunk, CourtRuleDocument
from app.services import document_service, embedding_service

logger = logging.getLogger("lexpar.knowledge")

DEFAULT_TOP_K = 4

# A chunk's leading section/rule heading, e.g. "Section 23", "SEC. 5", "Rule 8". Anchored to the
# chunk START and requiring a number — conservative on purpose: when a chunk does not open with a
# clearly recognizable heading, section_reference stays NULL rather than guessed.
_SECTION_HEADING = re.compile(
    r"^\s*(?P<kind>SECTION|SEC\.?|RULE)\s+(?P<num>\d+[A-Za-z]?)\b", re.IGNORECASE
)
_KIND_LABELS = {"SECTION": "Section", "SEC": "Sec.", "SEC.": "Sec.", "RULE": "Rule"}


def extract_section_reference(chunk: str) -> str | None:
    """The normalized heading a chunk clearly opens with ("Section 23" / "Sec. 5" / "Rule 8"),
    or None when not confidently extractable. Pure."""
    match = _SECTION_HEADING.match(chunk)
    if match is None:
        return None
    kind = _KIND_LABELS.get(match.group("kind").upper(), match.group("kind").title())
    return f"{kind} {match.group('num')}"


def create_rule_document_row(
    db: DbSession,
    court_id: uuid.UUID,
    title: str,
    storage_path: str,
    source_citation: str | None = None,
    source_reference: str | None = None,
    uploaded_by_user_id: uuid.UUID | None = None,
) -> CourtRuleDocument:
    document = CourtRuleDocument(
        id=uuid.uuid4(),
        court_id=court_id,
        title=title,
        source_citation=source_citation,
        source_reference=source_reference,
        storage_path=storage_path,
        ingestion_status="pending",
        uploaded_by_user_id=uploaded_by_user_id,
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


def ingest_rule_document(
    db: DbSession,
    document: CourtRuleDocument,
    raw_bytes: bytes,
    *,
    embedder=embedding_service.embed_texts,
) -> None:
    """Extract → chunk → embed → persist chunks (verbatim text only, with per-chunk section
    headings where confidently present). Sets ingestion_status to 'ready' or 'failed' (with the
    error) — never leaves it silently 'pending'."""
    try:
        text = document_service.extract_pdf_text(raw_bytes)
        if len(text.strip()) < document_service.MIN_EXTRACTED_CHARS:
            raise ValueError(
                "No extractable text found — this may be a scanned/image PDF. Please provide a "
                "text-based PDF from an official source."
            )
        chunks = document_service.chunk_text(text)
        vectors = embedder(chunks)
        if len(vectors) != len(chunks):
            raise ValueError("embedding count did not match chunk count")

        # Replace any prior chunks for this document (idempotent re-ingest).
        db.execute(
            delete(CourtRuleChunk).where(CourtRuleChunk.court_rule_document_id == document.id)
        )
        for index, (chunk_text, embedding) in enumerate(zip(chunks, vectors)):
            db.add(
                CourtRuleChunk(
                    court_rule_document_id=document.id,
                    court_id=document.court_id,
                    chunk_index=index,
                    chunk_text=chunk_text,
                    embedding=list(embedding),
                    section_reference=extract_section_reference(chunk_text),
                )
            )
        document.chunk_count = len(chunks)
        document.ingestion_status = "ready"
        document.error = None
        db.commit()
        logger.info("ingested rule document %s (%d chunks)", document.id, len(chunks))
    except Exception as exc:  # noqa: BLE001 — record the failure, don't crash the worker/route
        db.rollback()
        document.ingestion_status = "failed"
        document.error = str(exc)[:500]
        db.commit()
        logger.exception("ingestion failed for rule document %s", document.id)


def retrieve_rule_refs(
    db: DbSession,
    court_id: uuid.UUID,
    query: str,
    k: int = DEFAULT_TOP_K,
    *,
    embedder=embedding_service.embed_text,
) -> list[tuple[str, str]]:
    """Top-k (chunk_id, passage) pairs for a court, cosine-ranked. Each passage is the VERBATIM
    chunk text, prefixed with its section heading ("[Section 23] …") when one was extracted, so
    downstream prompts and the §13 citation cross-check can anchor citations to real headings;
    the chunk ids feed the provenance trail."""
    rows = db.scalars(
        select(CourtRuleChunk).where(CourtRuleChunk.court_id == court_id)
    ).all()
    if not rows or not query.strip():
        return []
    query_vec = embedder(query)
    candidates = [
        (
            (
                str(row.id),
                f"[{row.section_reference}] {row.chunk_text}"
                if row.section_reference
                else row.chunk_text,
            ),
            row.embedding,
        )
        for row in rows
    ]
    return embedding_service.top_k(query_vec, candidates, k)


def retrieve_rule_passages(
    db: DbSession,
    court_id: uuid.UUID,
    query: str,
    k: int = DEFAULT_TOP_K,
    *,
    embedder=embedding_service.embed_text,
) -> list[str]:
    """The passage texts only (see retrieve_rule_refs for the id-carrying variant)."""
    return [
        text
        for _chunk_id, text in retrieve_rule_refs(db, court_id, query, k, embedder=embedder)
    ]


def documents_for_court(db: DbSession, court_id: uuid.UUID) -> list[CourtRuleDocument]:
    return list(
        db.scalars(
            select(CourtRuleDocument).where(
                CourtRuleDocument.court_id == court_id,
                CourtRuleDocument.deleted_at.is_(None),
            )
        ).all()
    )


def as_status_dict(document: CourtRuleDocument) -> dict:
    return {
        "id": str(document.id),
        "title": document.title,
        "source_citation": document.source_citation,
        "source_reference": document.source_reference,
        "ingestion_status": document.ingestion_status,
        "chunk_count": document.chunk_count,
        "error": document.error,
    }
