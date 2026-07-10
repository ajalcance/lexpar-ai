"""
File: app/api/sessions.py
Purpose: Session routes — start a session for a case and fetch a session with its transcript.
Depends on: fastapi, app/services/{session,case}_service.py, app/security.py, app/schemas/session.py
Related: docs/ARCHITECTURE.md §5, frontend SparringRoom.tsx
Security notes: Both routes require a bearer token; creating a session validates that the case
    belongs to current_user before starting.
"""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session as DbSession

from app.db import get_db
from app.models.user import User
from app.schemas.session import SessionCreate, SessionDetailOut, SessionOut
from app.security import get_current_user
from app.services import case_service, session_service

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.post("", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
def create_session(
    payload: SessionCreate,
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> SessionOut:
    case = case_service.get_case(db, current_user, payload.case_id)
    return session_service.create_session(db, current_user, case, payload.proceeding_type)


@router.get("/{session_id}", response_model=SessionDetailOut)
def get_session(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> SessionDetailOut:
    return session_service.get_session(db, current_user, session_id)
