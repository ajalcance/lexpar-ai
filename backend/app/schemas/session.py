"""
File: app/schemas/session.py
Purpose: Pydantic shapes for sessions and their transcript lines. SessionOut is the summary;
    SessionDetailOut adds the ordered transcript for GET /api/sessions/{id}.
Depends on: pydantic
Related: app/api/sessions.py, app/services/session_service.py, app/models/{session,transcript}.py
Security notes: TranscriptOut.content is attorney work product — returned to the owning attorney
    only (routes enforce ownership), never logged.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.session import PROCEEDING_TYPES


class SessionCreate(BaseModel):
    case_id: uuid.UUID
    # §13 Phase 4: REQUIRED — which proceeding is being rehearsed drives the eligible objection
    # grounds. Validated against the model's PROCEEDING_TYPES (single source of truth, no Literal
    # duplicate).
    proceeding_type: str

    @field_validator("proceeding_type")
    @classmethod
    def _known_proceeding_type(cls, value: str) -> str:
        if value not in PROCEEDING_TYPES:
            raise ValueError(
                f"proceeding_type must be one of {', '.join(PROCEEDING_TYPES)}"
            )
        return value


class TranscriptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    speaker: str
    content: str
    was_interruption: bool
    spoken_at: datetime


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    case_id: uuid.UUID
    status: str
    # §13: which proceeding is being rehearsed. Creation input stays optional until the frontend
    # selector lands (Phase 4 makes it required at creation); the model defaults it meanwhile.
    proceeding_type: str
    llm_backend_used: str | None = None
    started_at: datetime
    ended_at: datetime | None = None


class SessionDetailOut(SessionOut):
    transcripts: list[TranscriptOut] = []
