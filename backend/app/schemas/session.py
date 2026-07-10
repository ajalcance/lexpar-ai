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

from pydantic import BaseModel, ConfigDict


class SessionCreate(BaseModel):
    case_id: uuid.UUID


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
