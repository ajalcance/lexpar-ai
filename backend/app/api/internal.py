"""
File: app/api/internal.py
Purpose: Internal, agent-only routes for persisting a session at its end (Gap 4) — mark it
    completed, and write the transcript batch + scorecard. Gated by the agent service credential
    (X-Agent-Token), which is a separate mechanism from user JWT auth and grants nothing else.
Depends on: fastapi, app/security_agent.py, app/services/agent_write_service.py, app/schemas/*
Related: docs/ARCHITECTURE.md §5, agents/backend_client.py
Security notes: Every route here requires the agent service token. No user is loaded; these routes
    are not for the browser client.
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DbSession

from app.db import get_db
from app.schemas.agent import ScorecardWriteIn, SessionContextOut
from app.schemas.scorecard import ScorecardOut
from app.schemas.session import SessionOut
from app.security_agent import require_agent_service
from app.services import agent_write_service

router = APIRouter(
    prefix="/api/sessions",
    tags=["internal"],
    dependencies=[Depends(require_agent_service)],
)


@router.get("/{session_id}/context", response_model=SessionContextOut)
def get_session_context(
    session_id: uuid.UUID,
    db: DbSession = Depends(get_db),
) -> SessionContextOut:
    return agent_write_service.get_session_context(db, session_id)


@router.post("/{session_id}/complete", response_model=SessionOut)
def complete_session(
    session_id: uuid.UUID,
    db: DbSession = Depends(get_db),
) -> SessionOut:
    return agent_write_service.complete_session(db, session_id)


@router.post("/{session_id}/scorecard", response_model=ScorecardOut, status_code=201)
def write_scorecard(
    session_id: uuid.UUID,
    payload: ScorecardWriteIn,
    db: DbSession = Depends(get_db),
) -> ScorecardOut:
    return agent_write_service.write_scorecard(db, session_id, payload)
