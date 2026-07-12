"""Case profile: structured user-stated case identity.

Adds to `cases` the fields the pleading alone cannot reliably supply and the agents were
guessing at (live failures: STT mishearing party names, "assumes facts" misfires on the case
number, a mis-framed matter, Opposing Counsel inventing which side to take): the docket/case
number, the parties as machine-readable fields, which side the attorney represents, and the
relief sought. All nullable — pre-profile cases keep working unchanged.

Revision ID: 0007_case_profile
Revises: 0006_scorecard_criteria
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0007_case_profile"
down_revision: str | None = "0006_scorecard_criteria"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cases", sa.Column("case_number", sa.String(), nullable=True))
    op.add_column("cases", sa.Column("petitioner", sa.String(), nullable=True))
    op.add_column("cases", sa.Column("respondent", sa.String(), nullable=True))
    op.add_column("cases", sa.Column("represented_party", sa.String(), nullable=True))
    op.add_column("cases", sa.Column("relief_sought", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("cases", "relief_sought")
    op.drop_column("cases", "represented_party")
    op.drop_column("cases", "respondent")
    op.drop_column("cases", "petitioner")
    op.drop_column("cases", "case_number")
