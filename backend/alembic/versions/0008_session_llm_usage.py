"""Add sessions.llm_usage — per-session LLM usage + canary counters (AUDIT B7/B8).

Written by the agents worker with the scorecard at session end (llm_metrics.snapshot():
{"roles": {...}, "canaries": {...}}). The billing/observability record — counts only, never
content. Nullable: sessions persisted by an older worker simply have no usage record.

Revision ID: 0008_session_llm_usage
Revises: 0007_case_profile
"""

import sqlalchemy as sa

from alembic import op

revision: str = "0008_session_llm_usage"
down_revision: str | None = "0007_case_profile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("llm_usage", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("sessions", "llm_usage")
