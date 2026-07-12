"""
File: app/api/cases.py
Purpose: Case routes — create, list, and fetch cases for the authenticated attorney.
Depends on: fastapi, app/services/case_service.py, app/security.py, app/schemas/case.py
Related: docs/ARCHITECTURE.md §5, frontend Dashboard.tsx / CaseUpload.tsx
Security notes: Every route requires a bearer token; the service scopes all data to current_user.
    Document upload to object storage is deferred — case_facts is JSON only for now.
"""

import uuid

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session as DbSession

from app.config import get_settings
from app.db import SessionLocal, get_db
from app.models.user import User
from app.schemas.case import CaseCreate, CaseDocumentOut, CaseOut
from app.schemas.session import SessionOut
from app.security import (
    get_current_user,
    require_admin,
    require_destructive_actions_enabled,
)
from app.services import (
    case_knowledge_service,
    case_service,
    session_service,
    storage_service,
)

router = APIRouter(prefix="/api/cases", tags=["cases"])


def _ingest_in_background(
    document_id: uuid.UUID, storage_path: str, supersedes_id: uuid.UUID | None = None
) -> None:
    """Runs after the upload response: fetch bytes, extract → chunk → embed → persist. Its own DB
    session (the request's is closed). Failures are recorded on the document row, not raised.
    `supersedes_id` = the Replace action: the old pleading is archived only on ingest success."""
    db = SessionLocal()
    try:
        from app.models.case_document import CaseDocument

        document = db.get(CaseDocument, document_id)
        if document is None:
            return
        raw = storage_service.get_object(storage_path)
        case_knowledge_service.ingest_document(
            db, document, raw, supersedes_document_id=supersedes_id
        )
    finally:
        db.close()


@router.post("", response_model=CaseOut, status_code=status.HTTP_201_CREATED)
def create_case(
    payload: CaseCreate,
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> CaseOut:
    return case_service.create_case(db, current_user, payload)


@router.get("", response_model=list[CaseOut])
def list_cases(
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> list[CaseOut]:
    return case_service.list_cases(db, current_user)


@router.get("/{case_id}", response_model=CaseOut)
def get_case(
    case_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> CaseOut:
    return case_service.get_case(db, current_user, case_id)


@router.get("/{case_id}/sessions", response_model=list[SessionOut])
def list_case_sessions(
    case_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> list[SessionOut]:
    """A case's rehearsal history — its sessions, newest first. 404 if the case isn't the
    attorney's (ownership check), so past scorecards are reachable from the case detail view."""
    case_service.get_case(db, current_user, case_id)  # 404/ownership check
    return session_service.list_sessions_for_case(db, current_user, case_id)


@router.post(
    "/{case_id}/documents", response_model=CaseDocumentOut, status_code=status.HTTP_202_ACCEPTED
)
async def upload_pleading(
    case_id: uuid.UUID,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> CaseDocumentOut:
    """Attach a pleading (PDF) to a case: store it, then ingest it (extract → chunk → embed) in the
    background so the agents can ground objections/rulings in it (§12). Returns immediately with a
    'pending' status the client polls."""
    case_service.get_case(db, current_user, case_id)  # 404/ownership check

    if file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(status_code=415, detail="Only PDF pleadings are supported.")
    data = await file.read()
    max_bytes = get_settings().max_upload_mb * 1024 * 1024
    if not data:
        raise HTTPException(status_code=422, detail="The uploaded file is empty.")
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=413, detail=f"File exceeds the {get_settings().max_upload_mb} MB limit."
        )

    key = storage_service.object_key(str(case_id), file.filename or "pleading.pdf")
    storage_service.put_object(key, data, content_type="application/pdf")
    document = case_knowledge_service.create_document_row(
        db, case_id, file.filename or "pleading.pdf", key, "application/pdf", len(data)
    )
    background.add_task(_ingest_in_background, document.id, key)
    return CaseDocumentOut(**case_knowledge_service.as_status_dict(document))


@router.get("/{case_id}/documents", response_model=list[CaseDocumentOut])
def list_pleadings(
    case_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> list[CaseDocumentOut]:
    """Ingestion status of each attached pleading (for the upload UI to poll)."""
    case_service.get_case(db, current_user, case_id)
    return [
        CaseDocumentOut(**case_knowledge_service.as_status_dict(d))
        for d in case_knowledge_service.documents_for(db, case_id)
    ]


@router.delete("/{case_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_pleading(
    case_id: uuid.UUID,
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> None:
    """SOFT tier for a pleading (owner action): excluded from retrieval via the document-state
    filter; rows/chunks/file kept so provenance stays resolvable."""
    case_service.get_case(db, current_user, case_id)  # 404/ownership
    document = case_knowledge_service.get_case_document(db, case_id, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Pleading not found.")
    case_knowledge_service.archive_case_document(db, document)


@router.post(
    "/{case_id}/documents/{document_id}/replace",
    response_model=CaseDocumentOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def replace_pleading(
    case_id: uuid.UUID,
    document_id: uuid.UUID,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> CaseDocumentOut:
    """Atomic Replace for a corrected version of the same pleading: the old version stays in
    retrieval until the new one ingests to 'ready' (then archived + lineage recorded). The case
    summary is last-writer-wins — correct for a replacement (§12 documented limitation for
    genuinely multi-document cases)."""
    case_service.get_case(db, current_user, case_id)
    old = case_knowledge_service.get_case_document(db, case_id, document_id)
    if old is None:
        raise HTTPException(status_code=404, detail="Pleading not found.")
    if old.deleted_at is not None:
        raise HTTPException(status_code=409, detail="This pleading is archived — upload anew.")

    if file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(status_code=415, detail="Only PDF pleadings are supported.")
    data = await file.read()
    max_bytes = get_settings().max_upload_mb * 1024 * 1024
    if not data:
        raise HTTPException(status_code=422, detail="The uploaded file is empty.")
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=413, detail=f"File exceeds the {get_settings().max_upload_mb} MB limit."
        )

    key = storage_service.object_key(str(case_id), file.filename or "pleading.pdf")
    storage_service.put_object(key, data, content_type="application/pdf")
    document = case_knowledge_service.create_document_row(
        db, case_id, file.filename or "pleading.pdf", key, "application/pdf", len(data)
    )
    background.add_task(_ingest_in_background, document.id, key, old.id)
    return CaseDocumentOut(**case_knowledge_service.as_status_dict(document))


@router.delete("/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_case(
    case_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
    _guard: None = Depends(require_destructive_actions_enabled),
) -> None:
    """SOFT tier (owner action, the default): the case disappears from lists/detail; sessions,
    scorecards, documents, and provenance stay intact. Reversible at the DB level."""
    case = case_service.get_case(db, current_user, case_id)
    case_service.archive_case(db, case)


@router.post("/{case_id}/purge", status_code=status.HTTP_204_NO_CONTENT)
def purge_case(
    case_id: uuid.UUID,
    _admin: User = Depends(require_admin),
    db: DbSession = Depends(get_db),
    _guard: None = Depends(require_destructive_actions_enabled),
) -> None:
    """HARD tier (ADMIN-only): genuinely delete the case and everything under it (sessions,
    transcripts, scorecards, provenance, documents, chunks, stored files). For test/mistake
    cases."""
    from app.models.case import Case

    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found.")
    case_service.purge_case(db, case)
