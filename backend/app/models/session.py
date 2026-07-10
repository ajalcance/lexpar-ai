"""
File: app/models/session.py
Purpose: SQLAlchemy model for the `sessions` table (ARCHITECTURE §8) — one rehearsal session
    against the AI Opposing Counsel + Judge. Status is a small state machine
    (in_progress → completed | abandoned) enforced in app/services/session_service.py.
Depends on: sqlalchemy, app/db.py
Related: app/schemas/session.py, app/services/session_service.py, app/models/transcript.py
Security notes: `deleted_at` supports soft deletes (DEV_GUIDELINES §8).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.transcript import Transcript

# Proceeding types (ARCHITECTURE §13). Plain strings + code-level constants, not sa.Enum —
# matches the house pattern for sessions.status and stays portable across Postgres/SQLite.
# MUST stay in sync with agents/objection_classifier.py PROCEEDING_ELIGIBLE_GROUNDS keys
# (agents is a separate package with no shared import; the cross-reference is deliberate).
PROCEEDING_TYPES = (
    "oral_argument",
    "direct_examination",
    "cross_examination",
    "motion_hearing",
)
DEFAULT_PROCEEDING_TYPE = "oral_argument"


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="in_progress")
    # What kind of proceeding is being rehearsed (§13) — drives which objection grounds are
    # eligible (agents PROCEEDING_ELIGIBLE_GROUNDS). Existing rows were backfilled to
    # oral_argument in migration 0003 (matches the scripted-mock history of this codebase).
    proceeding_type: Mapped[str] = mapped_column(
        String, nullable=False, default=DEFAULT_PROCEEDING_TYPE
    )
    llm_backend_used: Mapped[str | None] = mapped_column(String, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    transcripts: Mapped[list[Transcript]] = relationship(
        back_populates="session",
        order_by="Transcript.spoken_at",
        cascade="all, delete-orphan",
    )
