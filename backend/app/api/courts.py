"""
File: app/api/courts.py
Purpose: Court catalog + rule-corpus routes (§13). Creating a court and uploading rule documents
    are ADMIN-gated (role check, app/security.py require_admin); listing courts is open to any
    authenticated user (it feeds the case-creation dropdown). Rule upload stores the file and
    ingests it (extract → chunk → embed) in the background, same pattern as pleading upload.
Depends on: fastapi, app/security.py, app/services/{court_service,court_knowledge_service,
    storage_service}.py, app/schemas/court.py
Related: docs/ARCHITECTURE.md §13, scripts/seed_court.py, app/api/cases.py (the mirrored pattern)
Security notes: Only operator-supplied official documents enter this pipeline — the system never
    generates rule text. Admin gating is enforced server-side here; the frontend role check
    (Phase 6) is defense in depth, not the real control.
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

from app.config import get_settings
from app.db import SessionLocal, get_db
from app.models.user import User
from app.schemas.court import CourtCreate, CourtOut, CourtRuleDocumentOut, PurgeImpactOut
from app.security import get_current_user, require_admin
from app.services import court_knowledge_service, court_service, storage_service

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
    """Shared upload validation (upload + replace): PDF only, non-empty, within the size cap."""
    if file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(status_code=415, detail="Only PDF rule documents are supported.")
    data = await file.read()
    max_bytes = get_settings().max_upload_mb * 1024 * 1024
    if not data:
        raise HTTPException(status_code=422, detail="The uploaded file is empty.")
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=413, detail=f"File exceeds the {get_settings().max_upload_mb} MB limit."
        )
    return data


def _require_document(db: DbSession, court_id: uuid.UUID, document_id: uuid.UUID):
    document = court_knowledge_service.get_rule_document(db, court_id, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Rule document not found.")
    return document


@router.post("", response_model=CourtOut, status_code=status.HTTP_201_CREATED)
def create_court(
    payload: CourtCreate,
    _admin: User = Depends(require_admin),
    db: DbSession = Depends(get_db),
) -> CourtOut:
    return court_service.create_court(db, payload)


@router.get("", response_model=list[CourtOut])
def list_courts(
    include_archived: bool = False,
    user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> list[CourtOut]:
    """The active-court catalog for the case-creation dropdown — any authenticated user.
    `include_archived=true` is the ADMIN catalog (the /admin courts list): every forum including
    archived ones, so a retired court stays visible and purgeable instead of vanishing."""
    if include_archived:
        if user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Administrator role required for the full catalog.",
            )
        return court_service.list_all_courts(db)
    return court_service.list_active_courts(db)


@router.post(
    "/{court_id}/rules",
    response_model=CourtRuleDocumentOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_rule_document(
    court_id: uuid.UUID,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    source_citation: str | None = Form(default=None),
    source_reference: str | None = Form(default=None),
    admin: User = Depends(require_admin),
    db: DbSession = Depends(get_db),
) -> CourtRuleDocumentOut:
    """Upload an OFFICIAL rule document (PDF) for a court: store it, then ingest it in the
    background. `source_citation`/`source_reference` record the operator's stated provenance.
    Returns immediately with a 'pending' status the client polls."""
    court_service.get_court(db, court_id)  # 404 check
    data = await _validated_pdf(file)

    filename = file.filename or "rules.pdf"
    # courts/{court_id}/{filename} — object_key() hardcodes the cases/ prefix, so build directly
    # with the same sanitization.
    safe = filename.replace("/", "_").strip() or "rules.pdf"
    key = f"courts/{court_id}/{safe}"
    storage_service.put_object(key, data, content_type="application/pdf")
    document = court_knowledge_service.create_rule_document_row(
        db,
        court_id,
        title=title or filename,
        storage_path=key,
        source_citation=source_citation,
        source_reference=source_reference,
        uploaded_by_user_id=admin.id,
    )
    background.add_task(_ingest_in_background, document.id, key)
    return CourtRuleDocumentOut(**court_knowledge_service.as_status_dict(document))


@router.get("/{court_id}/rules", response_model=list[CourtRuleDocumentOut])
def list_rule_documents(
    court_id: uuid.UUID,
    _admin: User = Depends(require_admin),
    db: DbSession = Depends(get_db),
) -> list[CourtRuleDocumentOut]:
    """Every rule document incl. archived/superseded (admin corpus-management surface — the UI
    greys archived ones and offers Restore/Purge). Retrieval never sees archived chunks."""
    court_service.get_court(db, court_id)
    return [
        CourtRuleDocumentOut(**court_knowledge_service.as_status_dict(d))
        for d in court_knowledge_service.documents_for_court(db, court_id, include_archived=True)
    ]


@router.post(
    "/{court_id}/rules/{document_id}/replace",
    response_model=CourtRuleDocumentOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def replace_rule_document(
    court_id: uuid.UUID,
    document_id: uuid.UUID,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    source_citation: str | None = Form(default=None),
    source_reference: str | None = Form(default=None),
    admin: User = Depends(require_admin),
    db: DbSession = Depends(get_db),
) -> CourtRuleDocumentOut:
    """The atomic Replace action (§13 two-tier design): upload a corrected/newer version of an
    EXISTING document. The old version stays live in retrieval until the new one ingests to
    'ready' — only then is it archived (deleted_at + superseded_by_id), so a failed ingest never
    strands the court without its corpus, and old+new are never retrievable together."""
    court_service.get_court(db, court_id)
    old = _require_document(db, court_id, document_id)
    if old.deleted_at is not None:
        raise HTTPException(
            status_code=409, detail="This document is archived — restore it or upload anew."
        )
    data = await _validated_pdf(file)

    filename = file.filename or "rules.pdf"
    safe = filename.replace("/", "_").strip() or "rules.pdf"
    key = f"courts/{court_id}/{safe}"
    storage_service.put_object(key, data, content_type="application/pdf")
    document = court_knowledge_service.create_rule_document_row(
        db,
        court_id,
        title=title or old.title,
        storage_path=key,
        source_citation=source_citation or old.source_citation,
        source_reference=source_reference or old.source_reference,
        uploaded_by_user_id=admin.id,
    )
    background.add_task(_ingest_in_background, document.id, key, old.id)
    return CourtRuleDocumentOut(**court_knowledge_service.as_status_dict(document))


@router.delete("/{court_id}/rules/{document_id}", response_model=CourtRuleDocumentOut)
def archive_rule_document(
    court_id: uuid.UUID,
    document_id: uuid.UUID,
    _admin: User = Depends(require_admin),
    db: DbSession = Depends(get_db),
) -> CourtRuleDocumentOut:
    """SOFT tier: exclude from retrieval, keep everything (reversible; provenance resolvable)."""
    document = _require_document(db, court_id, document_id)
    court_knowledge_service.archive_rule_document(db, document)
    return CourtRuleDocumentOut(**court_knowledge_service.as_status_dict(document))


@router.post("/{court_id}/rules/{document_id}/restore", response_model=CourtRuleDocumentOut)
def restore_rule_document(
    court_id: uuid.UUID,
    document_id: uuid.UUID,
    _admin: User = Depends(require_admin),
    db: DbSession = Depends(get_db),
) -> CourtRuleDocumentOut:
    document = _require_document(db, court_id, document_id)
    try:
        court_knowledge_service.restore_rule_document(db, document)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return CourtRuleDocumentOut(**court_knowledge_service.as_status_dict(document))


@router.get("/{court_id}/rules/{document_id}/impact", response_model=PurgeImpactOut)
def rule_document_purge_impact(
    court_id: uuid.UUID,
    document_id: uuid.UUID,
    _admin: User = Depends(require_admin),
    db: DbSession = Depends(get_db),
) -> PurgeImpactOut:
    """The loud pre-purge warning: how many past rulings cite this document's chunks."""
    document = _require_document(db, court_id, document_id)
    return PurgeImpactOut(
        provenance_rulings=court_knowledge_service.provenance_count_for_document(db, document),
        chunk_count=document.chunk_count,
    )


@router.post("/{court_id}/rules/{document_id}/purge", status_code=status.HTTP_204_NO_CONTENT)
def purge_rule_document(
    court_id: uuid.UUID,
    document_id: uuid.UUID,
    _admin: User = Depends(require_admin),
    db: DbSession = Depends(get_db),
) -> None:
    """HARD tier: chunks + row + stored file, gone. Provenance rows survive as tombstones (their
    chunk-id strings stop resolving — the audit display degrades to counts, never errors)."""
    document = _require_document(db, court_id, document_id)
    court_knowledge_service.purge_rule_document(db, document)


@router.post("/{court_id}/archive", response_model=CourtOut)
def archive_court(
    court_id: uuid.UUID,
    _admin: User = Depends(require_admin),
    db: DbSession = Depends(get_db),
) -> CourtOut:
    """Retire a forum (soft): cascades soft-archive to its rule documents; referencing cases keep
    their court_id and simply run without rules grounding (fail-open)."""
    court = court_service.get_court(db, court_id)
    court_service.archive_court(db, court)
    return court


@router.post("/{court_id}/purge", status_code=status.HTTP_204_NO_CONTENT)
def purge_court(
    court_id: uuid.UUID,
    _admin: User = Depends(require_admin),
    db: DbSession = Depends(get_db),
) -> None:
    """HARD tier for a whole forum — 409 while ANY case references it (purge/reassign first).
    Fetches ARCHIVED-INCLUSIVE (plain db.get, not get_court, which filters archived rows) — an
    archived court must remain purgeable, otherwise it is an invisible, undeletable orphan."""
    from app.models.court import Court

    court = db.get(Court, court_id)
    if court is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Court not found.")
    court_service.purge_court(db, court)
