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
from app.schemas.court import CourtCreate, CourtOut, CourtRuleDocumentOut
from app.security import get_current_user, require_admin
from app.services import court_knowledge_service, court_service, storage_service

router = APIRouter(prefix="/api/courts", tags=["courts"])


def _ingest_in_background(document_id: uuid.UUID, storage_path: str) -> None:
    """Runs after the upload response: fetch bytes, extract → chunk → embed → persist. Its own DB
    session (the request's is closed). Failures are recorded on the document row, not raised."""
    db = SessionLocal()
    try:
        from app.models.court_rule import CourtRuleDocument

        document = db.get(CourtRuleDocument, document_id)
        if document is None:
            return
        raw = storage_service.get_object(storage_path)
        court_knowledge_service.ingest_rule_document(db, document, raw)
    finally:
        db.close()


@router.post("", response_model=CourtOut, status_code=status.HTTP_201_CREATED)
def create_court(
    payload: CourtCreate,
    _admin: User = Depends(require_admin),
    db: DbSession = Depends(get_db),
) -> CourtOut:
    return court_service.create_court(db, payload)


@router.get("", response_model=list[CourtOut])
def list_courts(
    _user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> list[CourtOut]:
    """The active-court catalog for the case-creation dropdown — any authenticated user."""
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
    """Ingestion status of each rule document (admin corpus-management surface)."""
    court_service.get_court(db, court_id)
    return [
        CourtRuleDocumentOut(**court_knowledge_service.as_status_dict(d))
        for d in court_knowledge_service.documents_for_court(db, court_id)
    ]
