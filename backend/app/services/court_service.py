"""
File: app/services/court_service.py
Purpose: Court catalog logic (§13) — create a court (admin action) and list/fetch active courts
    for the case-creation flow. The rule-corpus ingest/retrieval lives separately in
    court_knowledge_service.py (one responsibility per file).
Depends on: fastapi, sqlalchemy, app/models/court.py, app/schemas/court.py
Related: app/api/courts.py, app/services/court_knowledge_service.py, scripts/seed_court.py
Security notes: Court data is public information; the write path is admin-gated at the route
    (app/security.py require_admin), not here.
"""

import logging
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DbSession

from app.models.case import Case
from app.models.court import Court
from app.models.court_rule import CourtRuleChunk, CourtRuleDocument
from app.schemas.court import CourtCreate

logger = logging.getLogger("lexpar.courts")


def create_court(db: DbSession, data: CourtCreate) -> Court:
    court = Court(name=data.name, jurisdiction_description=data.jurisdiction_description)
    db.add(court)
    db.commit()
    db.refresh(court)
    return court


def list_active_courts(db: DbSession) -> list[Court]:
    """The catalog the case-creation dropdown shows: active, non-deleted courts."""
    stmt = (
        select(Court)
        .where(Court.is_active.is_(True), Court.deleted_at.is_(None))
        .order_by(Court.name)
    )
    return list(db.scalars(stmt))


def get_court(db: DbSession, court_id: uuid.UUID) -> Court:
    court = db.scalar(
        select(Court).where(Court.id == court_id, Court.deleted_at.is_(None))
    )
    if court is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Court not found.")
    return court


def archive_court(db: DbSession, court: Court) -> None:
    """SOFT tier: retire the forum. Cascades soft-archive to its rule documents so the whole
    corpus is structurally excluded from retrieval (one mechanism — the document-state filter).
    NOT blocked by referencing cases: they keep their court_id, their sessions simply retrieve no
    rules (the existing fail-open empty-block path), and the UI shows the forum as unavailable."""
    now = datetime.now(timezone.utc)
    court.deleted_at = now
    court.is_active = False
    documents = db.scalars(
        select(CourtRuleDocument).where(
            CourtRuleDocument.court_id == court.id, CourtRuleDocument.deleted_at.is_(None)
        )
    ).all()
    for document in documents:
        document.deleted_at = now
    db.commit()


def purge_court(db: DbSession, court: Court) -> None:
    """HARD tier: BLOCKED while any case (archived included — it could be restored) references
    this court; silently nulling a case's forum would mutate the case's meaning. Otherwise
    deletes chunks → documents → storage files → the court row."""
    referencing = db.scalars(select(Case).where(Case.court_id == court.id)).all()
    if referencing:
        titles = ", ".join(c.title for c in referencing[:5])
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"{len(referencing)} case(s) reference this court ({titles}"
                f"{'…' if len(referencing) > 5 else ''}). Purge or reassign them first."
            ),
        )
    documents = db.scalars(
        select(CourtRuleDocument).where(CourtRuleDocument.court_id == court.id)
    ).all()
    db.execute(delete(CourtRuleChunk).where(CourtRuleChunk.court_id == court.id))
    storage_paths = [d.storage_path for d in documents]
    for document in documents:
        db.delete(document)
    db.delete(court)
    db.commit()
    from app.services import storage_service

    for path in storage_paths:
        try:
            storage_service.delete_object(path)
        except Exception:  # noqa: BLE001 — best-effort
            logger.warning("could not delete stored object %s after court purge", path)
