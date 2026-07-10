"""Court & procedural-rules grounding: courts, court rule corpus, roles, proceeding types.

Adds the §13 grounding schema: `courts`, `court_rule_documents`, `court_rule_chunks` (operator-
supplied official rule text only — the system never generates rule content), plus three column
additions to existing tables:
- cases.court_id — nullable FK; pre-§13 rows keep NULL (no forced backfill of data we don't have).
- sessions.proceeding_type — NOT NULL, existing rows backfilled to 'oral_argument' (matches this
  codebase's scripted-mock history).
- users.role — NOT NULL, ALL existing rows explicitly set to 'attorney'; no user silently
  becomes admin.

Embeddings stay portable JSON (Postgres + SQLite), same as 0002's case_chunks.

Revision ID: 0003_court_grounding
Revises: 0002_case_knowledge_and_auth
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0003_court_grounding"
down_revision: str | None = "0002_case_knowledge_and_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "courts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("jurisdiction_description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "court_rule_documents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("court_id", sa.Uuid(), sa.ForeignKey("courts.id"), nullable=False, index=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("source_citation", sa.String(), nullable=True),
        sa.Column("source_reference", sa.String(), nullable=True),
        sa.Column("storage_path", sa.String(), nullable=False),
        sa.Column("ingestion_status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("uploaded_by_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "court_rule_chunks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "court_rule_document_id",
            sa.Uuid(),
            sa.ForeignKey("court_rule_documents.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("court_id", sa.Uuid(), sa.ForeignKey("courts.id"), nullable=False, index=True),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("embedding", sa.JSON(), nullable=False),
        sa.Column("section_reference", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )

    # cases.court_id — nullable for migration safety; new cases supply it once the catalog exists.
    op.add_column(
        "cases",
        sa.Column("court_id", sa.Uuid(), sa.ForeignKey("courts.id"), nullable=True, index=True),
    )

    # sessions.proceeding_type — server_default backfills every existing row on add; the explicit
    # UPDATE is belt-and-braces so the backfill intent survives even on a backend where the
    # default is not applied to existing rows.
    op.add_column(
        "sessions",
        sa.Column(
            "proceeding_type",
            sa.String(),
            nullable=False,
            server_default="oral_argument",
        ),
    )
    op.execute(
        "UPDATE sessions SET proceeding_type = 'oral_argument' WHERE proceeding_type IS NULL"
    )

    # users.role — every existing row EXPLICITLY becomes attorney; admin is never a default.
    op.add_column(
        "users",
        sa.Column("role", sa.String(), nullable=False, server_default="attorney"),
    )
    op.execute("UPDATE users SET role = 'attorney' WHERE role IS NULL")


def downgrade() -> None:
    op.drop_column("users", "role")
    op.drop_column("sessions", "proceeding_type")
    op.drop_column("cases", "court_id")
    op.drop_table("court_rule_chunks")
    op.drop_table("court_rule_documents")
    op.drop_table("courts")
