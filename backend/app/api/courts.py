"""
File: app/api/courts.py
Purpose: Court catalog + rule-corpus routes (§13). Courts are PER-USER (migration 0009): every
    route is scoped to the authenticated owner — you create, list, and manage only your own courts
    and their rule documents. Rule upload stores the file and ingests it (extract → chunk → embed)
    in the background, same pattern as pleading upload.
Depends on: fastapi, app/api/deps.py (get_owned_court), app/services/{court_service,
    court_knowledge_service,storage_service}.py, app/schemas/court.py
Related: docs/ARCHITECTURE.md §13, app/api/cases.py (the mirrored ownership pattern)
Security notes: Only owner-supplied official documents enter this pipeline — the system never
    generates rule text. Ownership is structural: {court_id} routes resolve through
    deps.get_owned_court (404 on a foreign court), so a new route cannot forget the check.
"""

import uuid

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session as DbSession

from app.api.deps import get_owned_court
from app.db import SessionLocal, get_db
from app.models.court import Court
from app.models.user import User
from app.schemas.court import CourtCreate, CourtOut, CourtRuleDocumentOut, PurgeImpactOut
from app.schemas.limits import LINE_MAX
from app.security import (
    get_current_user,
    require_destructive_actions_enabled,
)
from app.services import (
    court_knowledge_service,
    court_service,
    storage_service,
    upload_service,
)

router = APIRouter(prefix="/api/courts", tags=["courts"])


def _ingest_in_background(
    document_id: uuid.UUID, storage_path: str, supersedes_id: uuid.UUID | None = None
) -> None:
    """Runs after the upload response: fetch bytes, extract → chunk → embed → persist. Its own DB
    session (the request's is closed). Failures are recorded on the document row, not raised.
    `supersedes_id` = the Replace action: the old document is archived only on ingest success."""
    db = SessionLocal()
    try:
        from app.models.court_rule import CourtRuleDocument

        document = db.get(CourtRuleDocument, document_id)
        if document is None:
            return
        raw = storage_service.get_object(storage_path)
        court_knowledge_service.ingest_rule_document(
            db, document, raw, supersedes_document_id=supersedes_id
        )
    finally:
        db.close()


async def _validated_pdf(file: UploadFile) -> bytes:
    """Shared upload validation (upload + replace) — the hardened guardrails: PDF content-type +
    real %PDF- header, non-empty, and a streamed size cap that never buffers past the limit."""
    return await upload_service.read_pdf_upload(file)


def _require_document(db: DbSession, court_id: uuid.UUID, document_id: uuid.UUID):
    document = court_knowledge_service.get_rule_document(db, court_id, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Rule document not found.")
    return document


@router.post("", response_model=CourtOut, status_code=status.HTTP_201_CREATED)
def create_court(
    payload: CourtCreate,
    user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> CourtOut:
    return court_service.create_court(db, user, payload)


@router.get("", response_model=list[CourtOut])
def list_courts(
    include_archived: bool = False,
    user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> list[CourtOut]:
    """The user's OWN court catalog. Default = active courts (the case-creation dropdown);
    `include_archived=true` = the full management list including archived ones, so a retired court
    stays visible and purgeable instead of vanishing."""
    if include_archived:
        return court_service.list_all_courts(db, user)
    return court_service.list_active_courts(db, user)


@router.post(
    "/{court_id}/rules",
    response_model=CourtRuleDocumentOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_rule_document(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    title: str | None = Form(default=None, max_length=LINE_MAX),
    source_citation: str | None = Form(default=None, max_length=LINE_MAX),
    source_reference: str | None = Form(default=None, max_length=LINE_MAX),
    court: Court = Depends(get_owned_court),
    db: DbSession = Depends(get_db),
) -> CourtRuleDocumentOut:
    """Upload an OFFICIAL rule document (PDF) for one of your courts: store it, then ingest it in
    the background. `source_citation`/`source_reference` record the owner's stated provenance.
    Returns immediately with a 'pending' status the client polls."""
    data = await _validated_pdf(file)

    filename = file.filename or "rules.pdf"
    # courts/{court_id}/{filename} — object_key() hardcodes the cases/ prefix, so build directly
    # with the same sanitization.
    safe = filename.replace("/", "_").strip() or "rules.pdf"
    key = f"courts/{court.id}/{safe}"
    storage_service.put_object(key, data, content_type="application/pdf")
    document = court_knowledge_service.create_rule_document_row(
        db,
        court.id,
        title=title or filename,
        storage_path=key,
        source_citation=source_citation,
        source_reference=source_reference,
        uploaded_by_user_id=court.user_id,
    )
    background.add_task(_ingest_in_background, document.id, key)
    return CourtRuleDocumentOut(**court_knowledge_service.as_status_dict(document))


@router.get("/{court_id}/rules", response_model=list[CourtRuleDocumentOut])
def list_rule_documents(
    court: Court = Depends(get_owned_court),
    db: DbSession = Depends(get_db),
) -> list[CourtRuleDocumentOut]:
    """Every rule document incl. archived/superseded (the corpus-management surface — the UI greys
    archived ones and offers Restore/Purge). Retrieval never sees archived chunks."""
    return [
        CourtRuleDocumentOut(**court_knowledge_service.as_status_dict(d))
        for d in court_knowledge_service.documents_for_court(db, court.id, include_archived=True)
    ]


@router.post(
    "/{court_id}/rules/{document_id}/replace",
    response_model=CourtRuleDocumentOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def replace_rule_document(
    document_id: uuid.UUID,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    title: str | None = Form(default=None, max_length=LINE_MAX),
    source_citation: str | None = Form(default=None, max_length=LINE_MAX),
    source_reference: str | None = Form(default=None, max_length=LINE_MAX),
    court: Court = Depends(get_owned_court),
    db: DbSession = Depends(get_db),
) -> CourtRuleDocumentOut:
    """The atomic Replace action (§13 two-tier design): upload a corrected/newer version of an
    EXISTING document. The old version stays live in retrieval until the new one ingests to
    'ready' — only then is it archived (deleted_at + superseded_by_id), so a failed ingest never
    strands the court without its corpus, and old+new are never retrievable together."""
    old = _require_document(db, court.id, document_id)
    if old.deleted_at is not None:
        raise HTTPException(
            status_code=409, detail="This document is archived — restore it or upload anew."
        )
    data = await _validated_pdf(file)

    filename = file.filename or "rules.pdf"
    safe = filename.replace("/", "_").strip() or "rules.pdf"
    key = f"courts/{court.id}/{safe}"
    storage_service.put_object(key, data, content_type="application/pdf")
    document = court_knowledge_service.create_rule_document_row(
        db,
        court.id,
        title=title or old.title,
        storage_path=key,
        source_citation=source_citation or old.source_citation,
        source_reference=source_reference or old.source_reference,
        uploaded_by_user_id=court.user_id,
    )
    background.add_task(_ingest_in_background, document.id, key, old.id)
    return CourtRuleDocumentOut(**court_knowledge_service.as_status_dict(document))


@router.delete("/{court_id}/rules/{document_id}", response_model=CourtRuleDocumentOut)
def archive_rule_document(
    document_id: uuid.UUID,
    court: Court = Depends(get_owned_court),
    db: DbSession = Depends(get_db),
    _guard: None = Depends(require_destructive_actions_enabled),
) -> CourtRuleDocumentOut:
    """SOFT tier: exclude from retrieval, keep everything (reversible; provenance resolvable)."""
    document = _require_document(db, court.id, document_id)
    court_knowledge_service.archive_rule_document(db, document)
    return CourtRuleDocumentOut(**court_knowledge_service.as_status_dict(document))


@router.post("/{court_id}/rules/{document_id}/restore", response_model=CourtRuleDocumentOut)
def restore_rule_document(
    document_id: uuid.UUID,
    court: Court = Depends(get_owned_court),
    db: DbSession = Depends(get_db),
) -> CourtRuleDocumentOut:
    document = _require_document(db, court.id, document_id)
    try:
        court_knowledge_service.restore_rule_document(db, document)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return CourtRuleDocumentOut(**court_knowledge_service.as_status_dict(document))


@router.get("/{court_id}/rules/{document_id}/impact", response_model=PurgeImpactOut)
def rule_document_purge_impact(
    document_id: uuid.UUID,
    court: Court = Depends(get_owned_court),
    db: DbSession = Depends(get_db),
) -> PurgeImpactOut:
    """The loud pre-purge warning: how many past rulings cite this document's chunks."""
    document = _require_document(db, court.id, document_id)
    return PurgeImpactOut(
        provenance_rulings=court_knowledge_service.provenance_count_for_document(db, document),
        chunk_count=document.chunk_count,
    )


@router.post("/{court_id}/rules/{document_id}/purge", status_code=status.HTTP_204_NO_CONTENT)
def purge_rule_document(
    document_id: uuid.UUID,
    court: Court = Depends(get_owned_court),
    db: DbSession = Depends(get_db),
    _guard: None = Depends(require_destructive_actions_enabled),
) -> None:
    """HARD tier: chunks + row + stored file, gone. Provenance rows survive as tombstones (their
    chunk-id strings stop resolving — the audit display degrades to counts, never errors)."""
    document = _require_document(db, court.id, document_id)
    court_knowledge_service.purge_rule_document(db, document)


@router.post("/{court_id}/archive", response_model=CourtOut)
def archive_court(
    court: Court = Depends(get_owned_court),
    db: DbSession = Depends(get_db),
    _guard: None = Depends(require_destructive_actions_enabled),
) -> CourtOut:
    """Retire a forum (soft): cascades soft-archive to its rule documents; referencing cases keep
    their court_id and simply run without rules grounding (fail-open)."""
    court_service.archive_court(db, court)
    return court


@router.post("/{court_id}/purge", status_code=status.HTTP_204_NO_CONTENT)
def purge_court(
    court_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
    _guard: None = Depends(require_destructive_actions_enabled),
) -> None:
    """HARD tier for a whole forum — 409 while ANY case references it (purge/reassign first).
    Fetches ARCHIVED-INCLUSIVE but still OWNER-scoped (not get_owned_court, which filters archived
    rows) — an archived court must remain purgeable by its owner, never an invisible orphan, and
    never reachable by a non-owner."""
    court = db.get(Court, court_id)
    if court is None or court.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Court not found.")
    court_service.purge_court(db, court)
