"""
File: app/models/court.py
Purpose: SQLAlchemy model for the `courts` table (ARCHITECTURE §13) — a forum whose procedural
    rules ground the agents (e.g. a specific special commercial court). Cases reference a court;
    court-rule documents/chunks (app/models/court_rule.py) hang off it as the retrieval corpus.
Depends on: sqlalchemy, app/db.py
Related: app/models/court_rule.py, app/models/case.py (cases.court_id),
    app/services/court_knowledge_service.py (Phase 2), docs/ARCHITECTURE.md §13
Security notes: Court names/jurisdiction descriptions are public information — nothing here is
    attorney work product. Courts are OWNER-SCOPED (`user_id`, migration 0009): a user only ever
    sees/manages their own. `deleted_at` supports soft deletes (DEV_GUIDELINES §8); `is_active`
    additionally lets the owner retire a court from their case-creation catalog without deleting it.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Court(Base):
    __tablename__ = "courts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # The owner. Courts are per-user (migration 0009): each account creates and manages its own
    # courts + rule corpus, scoped exactly like its cases — there is no shared/global catalog.
    # Nullable only for legacy pre-0009 rows (there is no production data); every court the app
    # creates sets it, and every query filters by it.
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    jurisdiction_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def archived(self) -> bool:
        """Soft-archived (retired). Surfaced on the admin catalog (CourtOut.archived) so archived
        forums stay visible — and purgeable — instead of silently vanishing from the UI."""
        return self.deleted_at is not None
