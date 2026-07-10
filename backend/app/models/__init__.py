"""
File: app/models/__init__.py
Purpose: Import all ORM models so they register on Base.metadata (needed for Alembic
    autogeneration and for Base.metadata.create_all in tests).
Related: app/db.py (Base), alembic/env.py, tests/conftest.py
"""

from app.models.case import Case
from app.models.case_document import CaseChunk, CaseDocument
from app.models.court import Court
from app.models.court_rule import CourtRuleChunk, CourtRuleDocument
from app.models.ruling_provenance import RulingProvenance
from app.models.scorecard import Scorecard
from app.models.session import Session
from app.models.transcript import Transcript
from app.models.user import User

__all__ = [
    "User",
    "Case",
    "CaseDocument",
    "CaseChunk",
    "Court",
    "CourtRuleDocument",
    "CourtRuleChunk",
    "RulingProvenance",
    "Session",
    "Transcript",
    "Scorecard",
]
