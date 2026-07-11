"""
File: app/models/case_document.py
Purpose: SQLAlchemy models for the Case Knowledge Base (ARCHITECTURE §12) — an uploaded pleading
    (`case_documents`) and its embedded chunks (`case_chunks`) that ground the agents' objections
    and rulings in the actual filing.
Depends on: sqlalchemy, app/db.py
Related: app/services/case_knowledge_service.py, app/api/cases.py, agents/case_knowledge.py
Security notes: `case_chunks.content` is attorney work product (pleading text) — never logged.
    Embeddings are stored as a portable JSON array of floats (not a pgvector column) so the same
    models run on Postgres (prod) and SQLite (CI), and cosine ranking is done in Python; pgvector
    is the documented scale-up path (§12).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db import Base


class CaseDocument(Base):
    __tablename__ = "case_documents"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cases.id"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String, nullable=False)
    storage_path: Mapped[str] = mapped_column(String, nullable=False)  # object-storage key
    content_type: Mapped[str | None] = mapped_column(String, nullable=True)
    byte_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # ingestion lifecycle: 'pending' | 'ready' | 'failed'
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Set (alongside deleted_at) when replaced by a corrected upload (two-tier deletion design).
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("case_documents.id"), nullable=True
    )


class CaseChunk(Base):
    __tablename__ = "case_chunks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cases.id"), nullable=False, index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("case_documents.id"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    # SENSITIVE: pleading text — never logged.
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Portable embedding: JSON array of floats (len == settings.embedding_dim).
    embedding: Mapped[list[float]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
