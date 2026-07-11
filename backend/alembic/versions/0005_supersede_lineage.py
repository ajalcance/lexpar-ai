"""Supersede lineage for the two-tier deletion design (archive vs purge).

`superseded_by_id` on both document tables records WHICH newer upload replaced a document (set
alongside deleted_at by the atomic Replace action). Retrieval excludes chunks whose parent
document is soft-deleted — archive/supersede keeps rows resolvable for the RulingProvenance
audit trail; only Purge hard-deletes.

Revision ID: 0005_supersede_lineage
Revises: 0004_ruling_provenance
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0005_supersede_lineage"
down_revision: str | None = "0004_ruling_provenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "court_rule_documents",
        sa.Column(
            "superseded_by_id",
            sa.Uuid(),
            sa.ForeignKey("court_rule_documents.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "case_documents",
        sa.Column(
            "superseded_by_id", sa.Uuid(), sa.ForeignKey("case_documents.id"), nullable=True
        ),
    )


def downgrade() -> None:
    op.drop_column("case_documents", "superseded_by_id")
    op.drop_column("court_rule_documents", "superseded_by_id")
