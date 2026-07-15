"""
File: app/services/court_service.py
Purpose: Court catalog logic (§13) — create/list/fetch a user's OWN courts for the case-creation
    flow. Every query is scoped to the owner (user_id): courts are per-user (migration 0009), so a
    user only ever sees or touches courts they created. The rule-corpus ingest/retrieval lives
    separately in court_knowledge_service.py (one responsibility per file).
Depends on: fastapi, sqlalchemy, app/models/{court,user}.py, app/schemas/court.py
Related: app/api/courts.py, app/api/deps.py (get_owned_court), court_knowledge_service.py
Security notes: Owner-scoped. Court names/jurisdiction descriptions are public information, but the
    corpus is the owner's — every read/write here filters by user_id (least privilege).
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
from app.models.user import User
from app.schemas.court import CourtCreate

logger = logging.getLogger("lexpar.courts")


def create_court(db: DbSession, user: User, data: CourtCreate) -> Court:
    court = Court(
        user_id=user.id,
        name=data.name,
        jurisdiction_description=data.jurisdiction_description,
    )
    db.add(court)
    db.commit()
    db.refresh(court)
    return court


def list_active_courts(db: DbSession, user: User) -> list[Court]:
    """The catalog the case-creation dropdown shows: the user's own active, non-deleted courts."""
    stmt = (
        select(Court)
        .where(
            Court.user_id == user.id,
            Court.is_active.is_(True),
            Court.deleted_at.is_(None),
        )
        .order_by(Court.name)
    )
    return list(db.scalars(stmt))


def list_all_courts(db: DbSession, user: User) -> list[Court]:
    """The owner's full catalog: every court they own including archived ones (active first, then
    by name) — an archived forum must stay visible (and purgeable) instead of silently vanishing."""
    stmt = (
        select(Court)
        .where(Court.user_id == user.id)
        .order_by(Court.deleted_at.isnot(None), Court.name)
    )
    return list(db.scalars(stmt))


def get_court(db: DbSession, user: User, court_id: uuid.UUID) -> Court:
    """Fetch one of the user's own active courts, or 404 (a foreign/archived court is not found)."""
    court = db.scalar(
        select(Court).where(
            Court.id == court_id,
            Court.user_id == user.id,
            Court.deleted_at.is_(None),
        )
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
    storage_paths = list(
        db.scalars(
            select(CourtRuleDocument.storage_path).where(
                CourtRuleDocument.court_id == court.id
            )
        ).all()
    )
    # Core deletes ONLY, child→parent (same Postgres FK-order fix as the case purge — ORM
    # db.delete() without relationship() gives the flush no inter-mapper ordering; see LESSONS).
    # The single bulk documents delete also clears the superseded_by_id self-FK lineage safely:
    # all rows of the court go in one statement.
    db.execute(delete(CourtRuleChunk).where(CourtRuleChunk.court_id == court.id))
    db.execute(delete(CourtRuleDocument).where(CourtRuleDocument.court_id == court.id))
    db.execute(delete(Court).where(Court.id == court.id))
    db.commit()
    from app.services import storage_service

    for path in storage_paths:
        try:
            storage_service.delete_object(path)
        except Exception:  # noqa: BLE001 — best-effort
            logger.warning("could not delete stored object %s after court purge", path)
