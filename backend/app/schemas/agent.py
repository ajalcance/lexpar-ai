"""
File: app/schemas/agent.py
Purpose: Request shapes for the internal, agent-only session-write routes — the batch transcript
    and the scorecard the agents worker persists at session end.
Depends on: pydantic
Related: app/api/internal.py, app/services/agent_write_service.py, agents/scorecard_builder.py
Security notes: Carries transcript content (attorney work product) — accepted only from the agent
    service credential, never logged.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class TranscriptTurnIn(BaseModel):
    speaker: str  # 'attorney' | 'opposing_counsel' | 'judge'
    content: str
    was_interruption: bool = False
    spoken_at: datetime | None = None


class ScorecardWriteIn(BaseModel):
    overall_score: float = Field(ge=0, le=100)
    strengths: str
    weaknesses: str
    judge_ruling: str
    transcript: list[TranscriptTurnIn] = []


class SessionContextOut(BaseModel):
    """The case context the agents worker loads at room join to seed its SessionState."""

    case_facts: str = ""
    case_title: str = ""
