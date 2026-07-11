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


# A section heading at the START OF ANY LINE — used to split a document into complete provisions
# for section-aware chunking. `[ \t]*` (not \s*) so it anchors to a real line start, not across
# blank lines. Mirrors _SECTION_HEADING's vocabulary.
_SECTION_SPLIT = re.compile(r"(?im)^[ \t]*(?:SECTION|SEC\.?|RULE)\s+\d+[A-Za-z]?\b")

# Any section/rule reference in free text (a query or a stored heading), for exact-citation lookup.
# Treats Section / Sec. / § as ONE family (statutory section) distinct from Rule, so
# "Section 12" == "Sec. 12" == "§12". Ordered section-before-sec so the longer alt wins.
_CITATION_REF = re.compile(r"(?i)(section|sec|rule|§)\.?\s*(\d+[A-Za-z]?)")


def _section_keys(text: str) -> set[str]:
    """Canonical match keys ("section:12" / "rule:8") for every section/rule reference in `text`.
    Used to match a cited section in a query against a chunk's stored section_reference regardless
    of surface form (Section/Sec./§). Pure."""
    keys: set[str] = set()
    for match in _CITATION_REF.finditer(text):
        kind = match.group(1).lower()
        family = "rule" if kind.startswith("rule") else "section"
        keys.add(f"{family}:{match.group(2).lower()}")
    return keys


def chunk_rule_text(text: str) -> list[tuple[str, str | None]]:
    """Section-aware chunking for court rules (A): split at detected section headings so each chunk
    is a COMPLETE provision where possible, returning (chunk_text, section_reference) pairs.
      - A section that fits in one window → one chunk (its heading is the section_reference).
      - An OVERSIZED section → windowed sub-chunks, EACH stamped with the parent section heading
        (so mid-section sub-chunks are labeled, not NULL, and an exact-citation lookup returns the
        whole provision).
      - A leading span before the first heading, or a document with NO detectable headings →
        the generic windowed chunker with per-chunk heading detection (usually None). Degrades to
        the previous behavior; never fails. Pure/deterministic."""
    cleaned = document_service.normalize_text(text)
    if not cleaned:
        return []
    result: list[tuple[str, str | None]] = []

    def _windowed(span: str) -> None:
        for piece in document_service.chunk_text(span):
            result.append((piece, extract_section_reference(piece)))

    matches = list(_SECTION_SPLIT.finditer(cleaned))
    if not matches:
        _windowed(cleaned)
        return result
    # Preamble before the first heading (title/enacting clause), if any.
    if matches[0].start() > 0:
        _windowed(cleaned[: matches[0].start()])
    # Each section unit runs from its heading to the next heading (or end of document).
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(cleaned)
        unit = cleaned[start:end].strip()
        if not unit:
            continue
        heading = extract_section_reference(unit)  # the unit opens with its heading
        if len(unit) <= document_service.CHUNK_CHARS:
            result.append((unit, heading))  # a complete provision in one chunk
        else:
            for piece in document_service.chunk_text(unit):  # oversized → labeled sub-chunks
                result.append((piece, heading))
    return result


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
        # A: section-aware chunking — each pair is (verbatim chunk, section_reference), a complete
        # provision where possible; sub-chunks of an oversized section carry the parent heading.
        chunk_pairs = chunk_rule_text(text)
        texts = [chunk_text for chunk_text, _ref in chunk_pairs]
        vectors = embedder(texts)
        if len(vectors) != len(texts):
            raise ValueError("embedding count did not match chunk count")

        # Replace any prior chunks for this document (idempotent re-ingest).
        db.execute(
            delete(CourtRuleChunk).where(CourtRuleChunk.court_rule_document_id == document.id)
        )
        for index, ((chunk_text, section_ref), embedding) in enumerate(zip(chunk_pairs, vectors)):
            db.add(
                CourtRuleChunk(
                    court_rule_document_id=document.id,
                    court_id=document.court_id,
                    chunk_index=index,
                    chunk_text=chunk_text,
                    embedding=list(embedding),
                    section_reference=section_ref,
                )
            )
        document.chunk_count = len(chunk_pairs)
        document.ingestion_status = "ready"
        document.error = None
        db.commit()
        logger.info("ingested rule document %s (%d chunks)", document.id, len(chunk_pairs))
    except Exception as exc:  # noqa: BLE001 — record the failure, don't crash the worker/route
        db.rollback()
        document.ingestion_status = "failed"
        document.error = str(exc)[:500]
        db.commit()
        logger.exception("ingestion failed for rule document %s", document.id)


def _passage_text(row: CourtRuleChunk) -> str:
    """The VERBATIM chunk, prefixed with its section heading ("[Section 23] …") when one was
    extracted — so prompts and the §13 citation cross-check can anchor to a real heading."""
    if row.section_reference:
        return f"[{row.section_reference}] {row.chunk_text}"
    return row.chunk_text


def retrieve_rule_refs(
    db: DbSession,
    court_id: uuid.UUID,
    query: str,
    k: int = DEFAULT_TOP_K,
    *,
    embedder=None,
    min_score: float | None = None,
) -> list[tuple[str, str]]:
    """(chunk_id, passage) pairs for a court — a HYBRID of exact-citation lookup + relevance-floored
    semantic search (§13):
      - B (exact): chunks whose section_reference is cited in the query are returned
        deterministically (independent of embedding rank), ordered by chunk_index so an oversized
        section's sub-chunks come back as the whole provision. Bounded by k.
      - D (floor): the remaining slots are filled by cosine top-k WITH a relevance threshold, so a
        tenuous match is dropped rather than padded in — this can return FEWER than k, or nothing
        beyond the exact matches, which flows into the existing fail-open no-rules-block path.
    Chunk ids feed the provenance trail. `min_score` defaults to config rule_retrieval_min_score.
    `embedder` resolves at CALL time (not a def-time default) so a monkeypatched one is used."""
    if embedder is None:
        embedder = embedding_service.embed_text
    if min_score is None:
        from app.config import get_settings

        min_score = get_settings().rule_retrieval_min_score
    rows = list(db.scalars(select(CourtRuleChunk).where(CourtRuleChunk.court_id == court_id)).all())
    if not rows or not query.strip():
        return []

    query_keys = _section_keys(query)
    exact = (
        sorted(
            (
                row
                for row in rows
                if row.section_reference and (_section_keys(row.section_reference) & query_keys)
            ),
            key=lambda row: row.chunk_index,
        )[:k]
        if query_keys
        else []
    )
    exact_ids = {row.id for row in exact}

    query_vec = embedder(query)
    candidates = [
        ((str(row.id), _passage_text(row)), row.embedding)
        for row in rows
        if row.id not in exact_ids
    ]
    semantic = embedding_service.top_k(query_vec, candidates, k, min_score=min_score)
    return [(str(row.id), _passage_text(row)) for row in exact] + semantic


def retrieve_rule_passages(
    db: DbSession,
    court_id: uuid.UUID,
    query: str,
    k: int = DEFAULT_TOP_K,
    *,
    embedder=None,
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
