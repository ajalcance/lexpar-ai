"""
File: app/models/user.py
Purpose: SQLAlchemy model for the `users` table (ARCHITECTURE §8) — the attorney account.
Depends on: sqlalchemy, app/db.py
Related: app/schemas/auth.py (API shape), app/services/auth_service.py
Security notes: `password_hash` is NULL while AUTH_MODE=stub. When real auth lands, store only a
    hash, never a plaintext password. `deleted_at` supports soft deletes (DEV_GUIDELINES §8).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


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
