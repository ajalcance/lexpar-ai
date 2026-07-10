"""Case Knowledge Base + real auth: case_summary, case_documents, case_chunks.

Adds the pleading-RAG tables (ARCHITECTURE §12) and the cases.case_summary digest. Embeddings are
stored as JSON (portable across Postgres/SQLite); pgvector is the documented scale-up path.
`users.password_hash` already exists (0001) — real auth just populates it, no schema change.

Revision ID: 0002_case_knowledge_and_auth
Revises: 0001_initial
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0002_case_knowledge_and_auth"
down_revision: str | None = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cases", sa.Column("case_summary", sa.Text(), nullable=True))

    op.create_table(
        "case_documents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("cases.id"), nullable=False, index=True),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("storage_path", sa.String(), nullable=False),
        sa.Column("content_type", sa.String(), nullable=True),
        sa.Column("byte_size", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "case_chunks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("cases.id"), nullable=False, index=True),
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey("case_documents.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("case_chunks")
    op.drop_table("case_documents")
    op.drop_column("cases", "case_summary")
