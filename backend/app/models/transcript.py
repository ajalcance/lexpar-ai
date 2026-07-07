"""
File: app/models/transcript.py
Purpose: SQLAlchemy model for the `transcripts` table (ARCHITECTURE §8) — one spoken line in a
    session, tagged with the speaker and whether it interrupted the attorney.
Depends on: sqlalchemy, app/db.py
Related: app/schemas/session.py (TranscriptOut), app/models/session.py,
    agents/objection_classifier.py
Security notes: `content` is attorney work product — never log in plaintext (log session_id only).
"""

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.session import Session


class Transcript(Base):
    __tablename__ = "transcripts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id"), nullable=False)
    speaker: Mapped[str] = mapped_column(String, nullable=False)
    # SENSITIVE: attorney work product — never log in plaintext.
    content: Mapped[str] = mapped_column(Text, nullable=False)
    was_interruption: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    spoken_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    session: Mapped["Session"] = relationship(back_populates="transcripts")
