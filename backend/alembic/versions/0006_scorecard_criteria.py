"""Scorecard rubric criteria: the per-dimension performance breakdown.

Adds a JSON `criteria` column to `scorecards` holding the judge's 0-100 sub-scores per rubric
dimension ([{"name": str, "score": number}, ...]) — the scorecard's rubric bars. Additive and
backfilled to an empty list, so existing scorecards keep working (they simply show no breakdown).
JSON stays portable across Postgres/SQLite, same as ruling_provenance.

Revision ID: 0006_scorecard_criteria
Revises: 0005_supersede_lineage
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0006_scorecard_criteria"
down_revision: str | None = "0005_supersede_lineage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scorecards",
        sa.Column(
            "criteria",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("scorecards", "criteria")
