"""
File: app/services/agent_write_service.py
Purpose: The write side of the internal agent routes — complete a session, and (in one call at
    session end) persist the full transcript batch plus the scorecard. Batching avoids per-turn
    network round-trips inside the live voice loop (Gap 4).
Depends on: fastapi, sqlalchemy, app/models/*, app/schemas/agent.py, app/services/session_service.py
Related: app/api/internal.py
Security notes: Only reachable via the agent service credential. case_facts/transcript/scorecard
    content is attorney work product — persisted, never logged.
"""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.models.scorecard import Scorecard
from app.models.session import Session
from app.models.transcript import Transcript
from app.schemas.agent import ScorecardWriteIn
from app.services import session_service


def complete_session(db: DbSession, session_id: uuid.UUID) -> Session:
    """Mark a session completed (in_progress → completed, sets ended_at)."""
    session = session_service.get_session_by_id(db, session_id)
    return session_service.transition_status(db, session, "completed")


def write_scorecard(db: DbSession, session_id: uuid.UUID, data: ScorecardWriteIn) -> Scorecard:
    """Persist the transcript batch and the scorecard for a completed session (one call)."""
    session = session_service.get_session_by_id(db, session_id)
    if session.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Complete the session before writing its scorecard.",
        )
    if db.scalar(select(Scorecard).where(Scorecard.session_id == session.id)) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Scorecard already exists for this session.",
        )

    # Batch-insert the transcript. Preserve order: use each turn's spoken_at, else a monotonically
    # increasing server timestamp so GET /sessions/{id} returns them in the order they occurred.
    base = datetime.now(timezone.utc)
    for index, turn in enumerate(data.transcript):
        db.add(
            Transcript(
                session_id=session.id,
                speaker=turn.speaker,
                content=turn.content,
                was_interruption=turn.was_interruption,
                spoken_at=turn.spoken_at or (base + timedelta(microseconds=index)),
            )
        )

    scorecard = Scorecard(
        session_id=session.id,
        overall_score=data.overall_score,
        strengths=data.strengths,
        weaknesses=data.weaknesses,
        judge_ruling=data.judge_ruling,
    )
    db.add(scorecard)
    db.commit()
    db.refresh(scorecard)
    return scorecard
