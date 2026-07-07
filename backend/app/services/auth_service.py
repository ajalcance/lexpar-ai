"""
File: app/services/auth_service.py
Purpose: Authentication logic for the stubbed auth provider. Validates credentials and ensures
    the stub user row exists. AUTH_MODE=stub accepts only admin/admin; the JWT it leads to is
    verified for real on every request by app/security.py.
Depends on: fastapi, sqlalchemy, app/config.py, app/models/user.py
Related: app/api/auth.py, app/security.py
Security notes: admin/admin is a placeholder provider (ARCHITECTURE §11) — must be replaced
    before any real attorney data. Never log passwords.
"""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.config import get_settings
from app.models.user import User

STUB_USERNAME = "admin"
STUB_PASSWORD = "admin"
STUB_EMAIL = "admin@lexpar.ai"


def authenticate(db: DbSession, username: str, password: str) -> User:
    """Validate stub credentials and return the stub user, or raise 401/501."""
    settings = get_settings()
    if settings.auth_mode != "stub":
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Real auth is not implemented yet (AUTH_MODE != stub).",
        )
    if username != STUB_USERNAME or password != STUB_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )
    return ensure_stub_user(db)


def ensure_stub_user(db: DbSession) -> User:
    """Return the single stub user, creating it on first login."""
    user = db.scalar(select(User).where(User.email == STUB_EMAIL))
    if user is None:
        user = User(email=STUB_EMAIL, full_name="Demo Attorney", firm_name="Solo Practice")
        db.add(user)
        db.commit()
        db.refresh(user)
    return user
