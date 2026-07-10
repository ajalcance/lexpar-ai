"""Ruling provenance: the per-ruling audit trail (§13 Phase 5).

One row per AI ruling (inline objection rulings + the final ruling): which retrieved chunks were
actually in that ruling's prompt, and which citations in the output were flagged as ungrounded
(turn-scoped check). JSON columns stay portable across Postgres/SQLite, same as the embeddings.

Revision ID: 0004_ruling_provenance
Revises: 0003_court_grounding
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0004_ruling_provenance"
down_revision: str | None = "0003_court_grounding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ruling_provenance",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "session_id", sa.Uuid(), sa.ForeignKey("sessions.id"), nullable=False, index=True
        ),
        sa.Column("ruling_type", sa.String(), nullable=False),
        sa.Column("chunk_ids_used", sa.JSON(), nullable=False),
        sa.Column("citation_flags", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("ruling_provenance")
