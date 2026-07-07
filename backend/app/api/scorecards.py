"""
File: app/api/scorecards.py
Purpose: Scorecard route — GET /api/sessions/{id}/scorecard, available once the session is
    completed.
Depends on: fastapi, app/services/scorecard_service.py, app/security.py, app/schemas/scorecard.py
Related: docs/ARCHITECTURE.md §5, frontend Scorecard.tsx
Security notes: Requires a bearer token; the service enforces ownership + completion before
    returning work-product-derived content.
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DbSession

from app.db import get_db
from app.models.user import User
from app.schemas.scorecard import ScorecardOut
from app.security import get_current_user
from app.services import scorecard_service

router = APIRouter(prefix="/api/sessions", tags=["scorecards"])


@router.get("/{session_id}/scorecard", response_model=ScorecardOut)
def get_scorecard(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> ScorecardOut:
    return scorecard_service.get_scorecard(db, current_user, session_id)
