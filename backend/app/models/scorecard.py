"""
File: app/models/scorecard.py
Purpose: SQLAlchemy model for the `scorecards` table (ARCHITECTURE §8) — the post-session
    assessment written by the Judge agent (one per session).
Depends on: sqlalchemy, app/db.py
Related: app/schemas/scorecard.py, app/services/scorecard_service.py, agents/judge.py
Security notes: strengths / weaknesses / judge_ruling are derived from attorney work product —
    never log their contents.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Numeric, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db import Base


class Scorecard(Base):
    __tablename__ = "scorecards"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id"), unique=True, nullable=False
    )
    overall_score: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    # SENSITIVE: derived from attorney work product — never log in plaintext.
    strengths: Mapped[str | None] = mapped_column(Text, nullable=True)
    weaknesses: Mapped[str | None] = mapped_column(Text, nullable=True)
    judge_ruling: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Per-dimension rubric breakdown: [{"name": str, "score": number}, ...]. JSON stays portable
    # across Postgres/SQLite (same as ruling_provenance). Empty list when the judge gave no
    # breakdown; the scorecard UI simply shows no rubric bars then.
    criteria: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
