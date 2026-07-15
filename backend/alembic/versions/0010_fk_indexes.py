"""FK indexes on the hot query paths (AUDIT B5).

The fastest-growing / most-joined foreign keys had no index: transcripts.session_id (read/joined
by session on every scorecard render), cases.user_id + courts.user_id (owner-scoped list on every
page), and sessions.case_id + sessions.user_id (the case-list aggregate join and per-case history).
Cheap, portable (no pgvector — embeddings stay JSON so the schema still builds on SQLite in tests),
and always-good. Indexes already present on the chunk tables' court_id/case_id are untouched.

Revision ID: 0010_fk_indexes
Revises: 0009_per_user_no_roles
"""

from alembic import op

revision: str = "0010_fk_indexes"
down_revision: str | None = "0009_per_user_no_roles"
branch_labels = None
depends_on = None

_INDEXES = (
    ("ix_transcripts_session_id", "transcripts", "session_id"),
    ("ix_cases_user_id", "cases", "user_id"),
    ("ix_courts_user_id", "courts", "user_id"),
    ("ix_sessions_case_id", "sessions", "case_id"),
    ("ix_sessions_user_id", "sessions", "user_id"),
)


def upgrade() -> None:
    for name, table, column in _INDEXES:
        op.create_index(name, table, [column])


def downgrade() -> None:
    for name, table, _column in _INDEXES:
        op.drop_index(name, table_name=table)
