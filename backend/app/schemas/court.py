"""
File: app/schemas/court.py
Purpose: Pydantic shapes for the Court catalog and the court-rule-document corpus (§13) — court
    creation/listing and the ingestion status of uploaded rule documents.
Depends on: pydantic
Related: app/api/courts.py, app/services/{court_service,court_knowledge_service}.py,
    app/models/{court,court_rule}.py
Security notes: Court names and rule-document metadata are public information (official law and
    its provenance) — no work product flows through these shapes.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CourtCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    jurisdiction_description: str | None = Field(default=None, max_length=5_000)


class CourtOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    jurisdiction_description: str | None = None
    is_active: bool
    created_at: datetime


class CourtRuleDocumentOut(BaseModel):
    """Ingestion status of an uploaded rule document (mirrors CaseDocumentOut)."""

    id: str
    title: str
    source_citation: str | None = None
    source_reference: str | None = None
    ingestion_status: str  # 'pending' | 'ready' | 'failed'
    chunk_count: int
    error: str | None = None
