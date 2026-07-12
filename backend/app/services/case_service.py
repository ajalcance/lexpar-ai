"""
File: app/services/case_service.py
Purpose: Case business logic — create, list, and fetch cases, always scoped to the owning
    attorney and excluding soft-deleted rows.
Depends on: fastapi, sqlalchemy, app/models/case.py, app/schemas/case.py, app/models/user.py
Related: app/api/cases.py
Security notes: All queries filter by user_id (least privilege) so one attorney can never read
    another's cases. case_facts is never logged.
"""

import logging
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DbSession

from app.models.case import Case
from app.models.case_document import CaseChunk, CaseDocument
from app.models.court import Court
from app.models.ruling_provenance import RulingProvenance
from app.models.scorecard import Scorecard
from app.models.session import Session
from app.models.transcript import Transcript
from app.models.user import User
from app.schemas.case import CaseCreate

logger = logging.getLogger("lexpar.cases")


def create_case(db: DbSession, user: User, data: CaseCreate) -> Case:
    # §13: when a court is named it must be a real, active one — a case grounded in a
    # nonexistent/retired forum would silently produce ungrounded sessions later.
    if data.court_id is not None:
        court = db.scalar(
            select(Court).where(
                Court.id == data.court_id,
                Court.is_active.is_(True),
                Court.deleted_at.is_(None),
            )
        )
        if court is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Unknown or inactive court.",
            )
    case = Case(
        user_id=user.id,
        title=data.title,
        case_number=data.case_number,
        petitioner=data.petitioner,
        respondent=data.respondent,
        represented_party=data.represented_party,
        relief_sought=data.relief_sought,
        case_facts=data.case_facts,
        court_id=data.court_id,
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


def list_cases(db: DbSession, user: User) -> list[Case]:
    stmt = (
        select(Case)
        .where(Case.user_id == user.id, Case.deleted_at.is_(None))
        .order_by(Case.created_at.desc())
    )
    return list(db.scalars(stmt))


def get_case(db: DbSession, user: User, case_id: uuid.UUID) -> Case:
    stmt = select(Case).where(
        Case.id == case_id, Case.user_id == user.id, Case.deleted_at.is_(None)
    )
    case = db.scalar(stmt)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")
    return case


def archive_case(db: DbSession, case: Case) -> None:
    """SOFT tier (the default): the case disappears from lists/detail (both already filter
    deleted_at); sessions/scorecards/documents stay intact and provenance stays resolvable.
    Reversible at the DB level."""
    if case.deleted_at is None:
        case.deleted_at = datetime.now(timezone.utc)
        db.commit()


def purge_case(db: DbSession, case: Case) -> None:
    """HARD tier (admin-only at the route): genuinely delete the case and everything under it —
    provenance → scorecards → transcripts → sessions → chunks → documents → storage files → the
    case row. Ordered manually (no FK/ORM cascade exists, by audit); storage deletes best-effort.
    For a purged case the provenance rows go too: the audit trail of a session that no longer
    exists audits nothing."""
    session_ids = list(
        db.scalars(select(Session.id).where(Session.case_id == case.id)).all()
    )
    if session_ids:
        db.execute(
            delete(RulingProvenance).where(RulingProvenance.session_id.in_(session_ids))
        )
        db.execute(delete(Scorecard).where(Scorecard.session_id.in_(session_ids)))
        db.execute(delete(Transcript).where(Transcript.session_id.in_(session_ids)))
        db.execute(delete(Session).where(Session.id.in_(session_ids)))
    storage_paths = list(
        db.scalars(
            select(CaseDocument.storage_path).where(CaseDocument.case_id == case.id)
        ).all()
    )
    # Core deletes ONLY, in explicit child→parent order — each executes immediately. The previous
    # mix (Core for chunks, ORM db.delete() for documents + case) failed on real Postgres: with no
    # relationship() configured the ORM flush has no inter-mapper dependency and emitted
    # `DELETE FROM cases` before the documents delete → ForeignKeyViolation. Invisible in tests
    # until SQLite FK enforcement was turned on (conftest PRAGMA; see LESSONS).
    db.execute(delete(CaseChunk).where(CaseChunk.case_id == case.id))
    db.execute(delete(CaseDocument).where(CaseDocument.case_id == case.id))
    db.execute(delete(Case).where(Case.id == case.id))
    db.commit()
    from app.services import storage_service

    for path in storage_paths:
        try:
            storage_service.delete_object(path)
        except Exception:  # noqa: BLE001 — best-effort
            logger.warning("could not delete stored object %s after case purge", path)
