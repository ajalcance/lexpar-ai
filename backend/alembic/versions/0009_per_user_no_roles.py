"""Per-user ownership, no roles: drop users.role, add courts.user_id.

The product moved from a role model (attorney/admin + first-login admin bootstrap, §13) to
single-owner accounts: each account owns everything it creates — cases AND courts/rule corpus —
and there is no admin/attorney distinction. So:
  - drop `users.role` (the admin role + bootstrap are gone);
  - add `courts.user_id` (courts are now per-user, scoped like cases).

`courts.user_id` is nullable ONLY for any legacy pre-0009 rows (there is no production data —
the hackathon droplet was destroyed); every court the app creates sets it and every query filters
by it, so a NULL-owner court is simply invisible to everyone (an acceptable orphan).

Revision ID: 0009_per_user_no_roles
Revises: 0008_session_llm_usage
"""

import sqlalchemy as sa

from alembic import op

revision: str = "0009_per_user_no_roles"
down_revision: str | None = "0008_session_llm_usage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "courts",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
    )
    op.drop_column("users", "role")


def downgrade() -> None:
    # Restore the role column defaulting to attorney (the old default); the admin bootstrap and
    # any prior promotions are not reconstructable, so downgrade lands everyone as attorney.
    op.add_column(
        "users",
        sa.Column("role", sa.String(), nullable=False, server_default="attorney"),
    )
    op.drop_column("courts", "user_id")
