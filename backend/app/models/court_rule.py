"""
File: app/models/court_rule.py
Purpose: SQLAlchemy models for the court-rules corpus (ARCHITECTURE §13) — an operator-uploaded
    official rule document (`court_rule_documents`) and its embedded chunks (`court_rule_chunks`)
    that ground the agents' objections and rulings in the forum's actual procedural rules.
    Mirrors the Case Knowledge Base pattern (app/models/case_document.py): portable JSON
    embeddings (Postgres + SQLite), pending/ready/failed ingestion lifecycle.
Depends on: sqlalchemy, app/db.py
Related: app/models/court.py, app/models/case_document.py (the pattern this mirrors),
    app/services/court_knowledge_service.py (Phase 2), docs/ARCHITECTURE.md §13
Security notes: Deliberately NOT tagged `# SENSITIVE`: rule text is published, official, public
    law — not privileged attorney work product like `case_chunks.content` or
    `transcripts.content`. Tagging public statutes would dilute the tag's grep-value as the
    marker of fields that must never be logged (DEV_GUIDELINES §8). The provenance fields
    (`source_citation`, `source_reference`) record where the operator said the text came from —
    the system never generates or paraphrases rule text itself (build hard constraint).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db import Base


class CourtRuleDocument(Base):
    __tablename__ = "court_rule_documents"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    court_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("courts.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String, nullable=False)
    # Formal citation of the source instrument, e.g. "Republic Act No. 11232" — supplied by the
    # operator at upload, never synthesized.
    source_citation: Mapped[str | None] = mapped_column(String, nullable=True)
    # Where the operator says the document came from (URL or citation) — provenance metadata,
    # not fetched content.
    source_reference: Mapped[str | None] = mapped_column(String, nullable=True)
    storage_path: Mapped[str] = mapped_column(String, nullable=False)  # object-storage key
    # ingestion lifecycle: 'pending' | 'ready' | 'failed' (mirrors case_documents.status)
    ingestion_status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # The admin who uploaded it (role enforcement lives in the route dependency, Phase 2).
    # Nullable: seed-script ingests may run without a request user.
    uploaded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Set (alongside deleted_at) when this document was REPLACED by a newer version — the audit
    # lineage of the two-tier deletion design. A superseded document cannot be restored while its
    # replacement exists (that would put two versions of one instrument back into retrieval).
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("court_rule_documents.id"), nullable=True
    )


class CourtRuleChunk(Base):
    __tablename__ = "court_rule_chunks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    court_rule_document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("court_rule_documents.id"), nullable=False, index=True
    )
    # Denormalized so retrieval can query by court directly, without a join through documents.
    court_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("courts.id"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    # Portable embedding: JSON array of floats (same pattern as case_chunks.embedding).
    embedding: Mapped[list[float]] = mapped_column(JSON, nullable=False)
    # e.g. "Section 23", "Rule 8, Sec. 1" — extracted at ingest ONLY where the chunk clearly
    # starts with a recognizable heading; NULL when not confidently extractable (never guessed).
    section_reference: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
