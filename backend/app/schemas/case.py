"""
File: app/schemas/case.py
Purpose: Pydantic shapes for creating and returning cases.
Depends on: pydantic
Related: app/api/cases.py, app/services/case_service.py, app/models/case.py
Security notes: case_facts is attorney work product — validated here, never logged downstream.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CaseCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    case_facts: str | None = Field(default=None, max_length=100_000)
    # The forum whose rules ground this case (§13). Optional during the §13 rollout — the UI has
    # no Court selector until the catalog route + frontend land (Phases 2/6); it flips to
    # required then. Validated against an existing, active Court when provided (case_service).
    court_id: uuid.UUID | None = None


class CaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    case_facts: str | None = None
    case_summary: str | None = None
    court_id: uuid.UUID | None = None
    storage_path: str | None = None
    created_at: datetime


class CaseDocumentOut(BaseModel):
    """Ingestion status of an uploaded pleading (§12)."""

    id: str
    filename: str
    status: str  # 'pending' | 'ready' | 'failed'
    chunk_count: int
    error: str | None = None
