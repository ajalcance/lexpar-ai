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

# User roles (ARCHITECTURE §13). Strings + constants, not sa.Enum (portable, house style).
# `admin` gates the court/rule-corpus management routes (Phase 2) — never a default.
USER_ROLES = ("attorney", "admin")
DEFAULT_USER_ROLE = "attorney"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    # 'attorney' (default) | 'admin'. Migration 0003 set ALL pre-existing rows to attorney
    # explicitly — no user silently becomes admin; promotion is a deliberate operator action.
    role: Mapped[str] = mapped_column(String, nullable=False, default=DEFAULT_USER_ROLE)
    firm_name: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
