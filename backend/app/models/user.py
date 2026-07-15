"""
File: app/models/user.py
Purpose: SQLAlchemy model for the `users` table (ARCHITECTURE §8) — the attorney account.
Depends on: sqlalchemy, app/db.py
Related: app/schemas/auth.py (API shape), app/services/auth_service.py
Security notes: `password_hash` holds a bcrypt hash, never a plaintext password (a NULL hash can
    never authenticate — verify_password returns False on it). The column stays nullable only for
    legacy rows; all real accounts are created hashed via auth_service.register_user. `deleted_at`
    supports soft deletes (DEV_GUIDELINES §8).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

# Single-owner accounts (no roles). Each account is self-owned and self-contained: the person who
# signs up owns everything they create — their cases AND their courts/rule corpus — and can see or
# touch nothing outside it. There is no admin/attorney distinction (removed in migration 0009); the
# old §13 admin role + first-login bootstrap were dropped when the product moved to per-user
# ownership. (Multi-user org accounts + RBAC remain a future, opt-in direction, not this model.)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    firm_name: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
