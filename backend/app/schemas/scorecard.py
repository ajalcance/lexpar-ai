"""
File: app/schemas/scorecard.py
Purpose: Pydantic response shape for a session scorecard.
Depends on: pydantic
Related: app/api/scorecards.py, app/services/scorecard_service.py, app/models/scorecard.py
Security notes: Fields derive from attorney work product — returned to the owning attorney only.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ScorecardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    overall_score: float | None = None
    strengths: str | None = None
    weaknesses: str | None = None
    judge_ruling: str | None = None
    created_at: datetime


class ProvenanceOut(BaseModel):
    """§13 audit trail for one AI ruling — read by the owning attorney on the scorecard page to
    distinguish grounded citations from flagged (ungrounded) ones."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ruling_type: str  # 'objection_ruling' | 'final_ruling'
    chunk_ids_used: list[str] = []
    citation_flags: list[str] = []
    created_at: datetime
