"""
File: app/models/case.py
Purpose: SQLAlchemy model for the `cases` table (ARCHITECTURE §8) — a case an attorney prepares.
Depends on: sqlalchemy, app/db.py
Related: app/schemas/case.py, app/services/case_service.py, frontend CaseUpload.tsx (the UI)
Security notes: `case_facts` is attorney work product — never log its contents (log case_id only).
    `storage_path` will point at object storage once document upload is wired. `deleted_at`
    supports soft deletes (DEV_GUIDELINES §8).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    # The forum whose procedural rules ground this case's sessions (ARCHITECTURE §13). Nullable
    # at the DB level for migration safety (pre-§13 rows have no court); new case creation
    # supplies it once the Court catalog + selector exist (Phases 2/6).
    court_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("courts.id"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String, nullable=False)
    # Case profile (migration 0007): structured, USER-STATED ground truth the pleading alone can't
    # supply reliably — the docket number, machine-readable parties (STT keyterms + matter
    # framing), WHICH SIDE the attorney represents (Opposing Counsel takes the opposite side by
    # declaration, never inference), and the relief sought (what the matter and the judge's
    # assessment anchor to). All nullable: pre-profile cases behave exactly as before.
    case_number: Mapped[str | None] = mapped_column(String, nullable=True)
    petitioner: Mapped[str | None] = mapped_column(String, nullable=True)
    respondent: Mapped[str | None] = mapped_column(String, nullable=True)
    # 'petitioner' | 'respondent' (validated at the schema)
    represented_party: Mapped[str | None] = mapped_column(String, nullable=True)
    relief_sought: Mapped[str | None] = mapped_column(Text, nullable=True)
    # SENSITIVE: attorney work product — never log in plaintext. Optional additional context now;
    # the pleading (§12) is the primary source of case substance.
    case_facts: Mapped[str | None] = mapped_column(Text, nullable=True)
    # SENSITIVE: the LLM-extracted structured digest of the pleading (§12), always in agent context.
    case_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    storage_path: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
