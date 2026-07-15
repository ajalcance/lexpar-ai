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
from sqlalchemy import and_, delete, func, select
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
    # §13: when a court is named it must be a real, active one THE USER OWNS — courts are per-user
    # (migration 0009), so a case can only be grounded in one of the owner's own forums; a
    # nonexistent/retired/foreign court would silently produce ungrounded sessions later.
    if data.court_id is not None:
        court = db.scalar(
            select(Court).where(
                Court.id == data.court_id,
                Court.user_id == user.id,
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
    """The owner's cases, each carrying a rehearsal summary (session count, best score, last
    rehearsal) computed in ONE grouped query — not an N+1 of per-case session fetches (AUDIT B5;
    the summary drives the Dashboard cards). The aggregate fields ride as transient attributes that
    CaseOut reads via from_attributes; get_case (detail) leaves them unset (None)."""
    stmt = (
        select(
            Case,
            func.count(func.distinct(Session.id)).label("session_count"),
            func.max(Scorecard.overall_score).label("best_score"),
            func.max(Session.started_at).label("last_rehearsed_at"),
        )
        .outerjoin(
            Session, and_(Session.case_id == Case.id, Session.deleted_at.is_(None))
        )
        .outerjoin(Scorecard, Scorecard.session_id == Session.id)
        .where(Case.user_id == user.id, Case.deleted_at.is_(None))
        .group_by(Case.id)
        .order_by(Case.created_at.desc())
    )
    cases: list[Case] = []
    for case, session_count, best_score, last_rehearsed_at in db.execute(stmt):
        case.session_count = int(session_count or 0)
        case.best_score = float(best_score) if best_score is not None else None
        case.last_rehearsed_at = last_rehearsed_at
        cases.append(case)
    return cases


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
