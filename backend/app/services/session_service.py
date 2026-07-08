"""
File: app/services/session_service.py
Purpose: Session business logic, including the session status state machine
    (in_progress → completed | abandoned; terminal states are final). This transition logic is
    covered by tests/test_sessions.py per DEV_GUIDELINES §6.
Depends on: fastapi, sqlalchemy, app/models/session.py, app/models/case.py, app/config.py
Related: app/api/sessions.py, app/services/scorecard_service.py
Security notes: Queries are scoped to the owning attorney (least privilege).
"""

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.config import get_settings
from app.models.case import Case
from app.models.session import Session
from app.models.user import User

VALID_STATUSES = {"in_progress", "completed", "abandoned"}

# From each status, the set of statuses it may transition to. Terminal states map to empty sets.
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "in_progress": {"completed", "abandoned"},
    "completed": set(),
    "abandoned": set(),
}


def create_session(db: DbSession, user: User, case: Case) -> Session:
    """Start a new in-progress session for a case, recording the active LLM backend."""
    settings = get_settings()
    session = Session(
        case_id=case.id,
        user_id=user.id,
        status="in_progress",
        llm_backend_used=settings.opposing_counsel_llm_provider,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_session(db: DbSession, user: User, session_id: uuid.UUID) -> Session:
    stmt = select(Session).where(
        Session.id == session_id,
        Session.user_id == user.id,
        Session.deleted_at.is_(None),
    )
    session = db.scalar(stmt)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")
    return session


def get_session_by_id(db: DbSession, session_id: uuid.UUID) -> Session:
    """Fetch a session by id without user scoping — for internal (agent) routes only."""
    stmt = select(Session).where(Session.id == session_id, Session.deleted_at.is_(None))
    session = db.scalar(stmt)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")
    return session


def transition_status(db: DbSession, session: Session, new_status: str) -> Session:
    """Move a session to a new status, enforcing the allowed transitions."""
    if new_status not in VALID_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown session status: {new_status}",
        )
    if new_status not in ALLOWED_TRANSITIONS[session.status]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot move a {session.status} session to {new_status}.",
        )
    session.status = new_status
    if new_status in {"completed", "abandoned"}:
        session.ended_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(session)
    return session
