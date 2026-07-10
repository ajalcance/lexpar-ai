"""
File: app/models/ruling_provenance.py
Purpose: SQLAlchemy model for the `ruling_provenance` table (ARCHITECTURE §13 Phase 5) — the
    audit trail behind every AI ruling: which retrieved chunks (case + court, prefixed
    "case:"/"court:") were actually in the prompt for that ruling, and which citations in the
    model's output were flagged as ungrounded (not present in what it was shown). This is what
    lets a session's output be DEFENDED to an attorney or client later — per-ruling evidence,
    not a debugging log.
Depends on: sqlalchemy, app/db.py
Related: app/api/internal.py (the agent-authed write route), agents/citation_check.py,
    agents/judge.py (produces the flags), docs/ARCHITECTURE.md §13
Security notes: Holds chunk ids and citation LABELS only (e.g. "Section 23") — no ruling text,
    no transcript content, no work product.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db import Base

RULING_TYPES = ("objection_ruling", "final_ruling")


class RulingProvenance(Base):
    __tablename__ = "ruling_provenance"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id"), nullable=False, index=True
    )
    ruling_type: Mapped[str] = mapped_column(String, nullable=False)
    # The chunks actually included in this ruling's prompt, "case:<uuid>" / "court:<uuid>".
    chunk_ids_used: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    # Citations in the output NOT present in those chunks (turn-scoped; labels only).
    citation_flags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
