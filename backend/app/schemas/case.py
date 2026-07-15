"""
File: app/schemas/case.py
Purpose: Pydantic shapes for creating and returning cases.
Depends on: pydantic
Related: app/api/cases.py, app/services/case_service.py, app/models/case.py
Security notes: case_facts is attorney work product — validated here, never logged downstream.
"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.limits import LINE_MAX, TEXT_MAX


class CaseCreate(BaseModel):
    title: str = Field(min_length=1, max_length=LINE_MAX)
    # Case profile — structured, user-stated identity the pleading can't reliably supply (which
    # side the attorney is on, the relief they seek) or that must be machine-readable (parties
    # for STT keyterms, the docket number for the record). Optional at the API for compatibility;
    # the UI requires the ones that drive the courtroom (parties, side, relief). Length-capped
    # (limits.py) — these flow into every LLM prompt, so an unbounded field is a cost/DoS vector.
    case_number: str | None = Field(default=None, max_length=LINE_MAX)
    petitioner: str | None = Field(default=None, max_length=LINE_MAX)
    respondent: str | None = Field(default=None, max_length=LINE_MAX)
    represented_party: Literal["petitioner", "respondent"] | None = None
    relief_sought: str | None = Field(default=None, max_length=TEXT_MAX)
    case_facts: str | None = Field(default=None, max_length=TEXT_MAX)
    # The forum whose rules ground this case (§13). Optional during the §13 rollout — the UI has
    # no Court selector until the catalog route + frontend land (Phases 2/6); it flips to
    # required then. Validated against an existing, active Court when provided (case_service).
    court_id: uuid.UUID | None = None


class CaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    case_number: str | None = None
    petitioner: str | None = None
    respondent: str | None = None
    represented_party: str | None = None
    relief_sought: str | None = None
    case_facts: str | None = None
    case_summary: str | None = None
    court_id: uuid.UUID | None = None
    storage_path: str | None = None
    created_at: datetime
    # Rehearsal summary — populated on the LIST (case_service.list_cases, one grouped query) so the
    # Dashboard cards need no per-case fetch (AUDIT B5, N+1). None on the detail route (get_case),
    # which doesn't use them.
    session_count: int | None = None
    best_score: float | None = None
    last_rehearsed_at: datetime | None = None


class CaseDocumentOut(BaseModel):
    """Ingestion status of an uploaded pleading (§12)."""

    id: str
    filename: str
    status: str  # 'pending' | 'ready' | 'failed'
    chunk_count: int
    error: str | None = None
