"""
File: app/services/auth_service.py
Purpose: Authentication logic. Two modes (config.auth_mode):
    - "production": real password auth — credentials are verified against the bcrypt hash in
      users.password_hash; users are created via register_user (hashed). This is what must be on
      before any real attorney/case data (ARCHITECTURE §11).
    - "stub": the legacy admin/admin demo path, kept for local dev only.
    Either way the JWT it leads to is verified for real on every request by app/security.py.
Depends on: fastapi, sqlalchemy, app/config.py, app/models/user.py, app/security_password.py
Related: app/api/auth.py, app/security.py, app/security_password.py
Security notes: Never log passwords. Production login is a bcrypt verify; the stub path is gated to
    AUTH_MODE=stub and creates a password-less demo user (which production auth would reject).
"""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.config import get_settings
from app.models.user import User
from app.security_password import hash_password, verify_password

STUB_USERNAME = "admin"
STUB_PASSWORD = "admin"
STUB_EMAIL = "admin@lexpar.ai"

_INVALID = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password."
)


def authenticate(db: DbSession, username: str, password: str) -> User:
    """Validate credentials and return the user, or raise 401."""
    settings = get_settings()
    if settings.auth_mode == "stub":
        return _authenticate_stub(db, username, password)
    return _authenticate_production(db, username, password)


def _authenticate_production(db: DbSession, email: str, password: str) -> User:
    """Real auth: look up by email (case-insensitive), verify the bcrypt hash."""
    user = db.scalar(
        select(User).where(User.email == email.strip().lower(), User.deleted_at.is_(None))
    )
    if user is None or not verify_password(password, user.password_hash):
        raise _INVALID
    return user


def register_user(
    db: DbSession,
    email: str,
    password: str,
    full_name: str | None = None,
    firm_name: str | None = None,
) -> User:
    """Create a user with a hashed password (production auth). Rejects a duplicate email."""
    normalized = email.strip().lower()
    if not normalized or "@" not in normalized:
        raise HTTPException(status_code=422, detail="A valid email is required.")
    existing = db.scalar(select(User).where(User.email == normalized))
    if existing is not None:
        raise HTTPException(status_code=409, detail="An account with that email already exists.")
    user = User(
        email=normalized,
        full_name=full_name,
        firm_name=firm_name,
        password_hash=hash_password(password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _authenticate_stub(db: DbSession, username: str, password: str) -> User:
    """Legacy demo path (local dev only) — admin/admin, a password-less user row."""
    if username != STUB_USERNAME or password != STUB_PASSWORD:
        raise _INVALID
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
