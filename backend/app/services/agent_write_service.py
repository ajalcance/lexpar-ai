"""
File: app/services/agent_write_service.py
Purpose: The read + write side of the internal agent routes — read a session's case context at room
    join, complete a session, and (in one call at session end) persist the full transcript batch
    plus the scorecard. Batching avoids per-turn network round-trips inside the live voice loop
    (Gap 4).
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

from app.models.case import Case
from app.models.scorecard import Scorecard
from app.models.session import Session
from app.models.transcript import Transcript
from app.schemas.agent import ScorecardWriteIn, SessionContextOut
from app.services import session_service


def get_session_context(db: DbSession, session_id: uuid.UUID) -> SessionContextOut:
    """Return the case facts for a session so the worker can seed its SessionState at room join."""
    session = session_service.get_session_by_id(db, session_id)
    case = db.get(Case, session.case_id)
    return SessionContextOut(
        case_facts=(case.case_facts if case and case.case_facts else ""),
        case_title=(case.title if case else ""),
        case_summary=(case.case_summary if case and case.case_summary else ""),
        court_id=(str(case.court_id) if case and case.court_id else ""),
        proceeding_type=session.proceeding_type or "",
        case_number=(case.case_number if case and case.case_number else ""),
        petitioner=(case.petitioner if case and case.petitioner else ""),
        respondent=(case.respondent if case and case.respondent else ""),
        represented_party=(
            case.represented_party if case and case.represented_party else ""
        ),
        relief_sought=(case.relief_sought if case and case.relief_sought else ""),
    )


def get_session_knowledge(db: DbSession, session_id: uuid.UUID, query: str, k: int = 5):
    """Case-knowledge retrieval for a session (§12): the pleading summary + query-relevant passages.
    Imported lazily to keep the write service free of embedding/knowledge deps at import."""
    from app.schemas.agent import KnowledgeOut
    from app.services import case_knowledge_service

    session = session_service.get_session_by_id(db, session_id)
    payload = case_knowledge_service.context_payload(db, session.case_id, query, k)
    return KnowledgeOut(**payload)


def get_court_rules(db: DbSession, session_id: uuid.UUID, query: str, k: int = 4):
    """Court-rules retrieval for a session (§13): the query-relevant VERBATIM rule passages of the
    forum the session's case names, with the chunk ids that produced them (provenance). Empty when
    the case names no court or the court has no ingested corpus — the agents fail open."""
    from app.schemas.agent import CourtRulesOut
    from app.services import court_knowledge_service

    session = session_service.get_session_by_id(db, session_id)
    case = db.get(Case, session.case_id)
    if case is None or case.court_id is None:
        return CourtRulesOut(passages=[], chunk_ids=[])
    refs = court_knowledge_service.retrieve_rule_refs(db, case.court_id, query, k)
    return CourtRulesOut(
        passages=[text for _chunk_id, text in refs],
        chunk_ids=[chunk_id for chunk_id, _text in refs],
    )


def write_provenance(db: DbSession, session_id: uuid.UUID, data) -> uuid.UUID:
    """Persist the §13 audit-trail row for one ruling. Validates the ruling type; the session must
    exist (404 otherwise). Returns the new row's id (the ruling's audit identifier)."""
    from app.models.ruling_provenance import RULING_TYPES, RulingProvenance

    session = session_service.get_session_by_id(db, session_id)
    if data.ruling_type not in RULING_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"ruling_type must be one of {', '.join(RULING_TYPES)}",
        )
    row = RulingProvenance(
        session_id=session.id,
        ruling_type=data.ruling_type,
        chunk_ids_used=list(data.chunk_ids_used),
        citation_flags=list(data.citation_flags),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row.id


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
        criteria=[{"name": c.name, "score": c.score} for c in data.criteria],
    )
    db.add(scorecard)
    db.commit()
    db.refresh(scorecard)
    return scorecard
