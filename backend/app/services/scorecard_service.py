"""
File: app/services/scorecard_service.py
Purpose: Scorecard retrieval — returns a session's scorecard, gated on the session being
    completed. (Scorecard *generation* is the Judge agent's job; the backend only stores/serves.)
Depends on: fastapi, sqlalchemy, app/services/session_service.py, app/models/scorecard.py
Related: app/api/scorecards.py, agents/judge.py
Security notes: Reuses session_service.get_session for the ownership check before returning any
    work-product-derived content.
"""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.models.scorecard import Scorecard
from app.models.user import User
from app.services import session_service


def get_scorecard(db: DbSession, user: User, session_id: uuid.UUID) -> Scorecard:
    session = session_service.get_session(db, user, session_id)
    if session.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Scorecard is available only after the session is completed.",
        )
    scorecard = db.scalar(select(Scorecard).where(Scorecard.session_id == session.id))
    if scorecard is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scorecard not found for this session.",
        )
    return scorecard
