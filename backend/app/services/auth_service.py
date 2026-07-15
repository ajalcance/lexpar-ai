"""
File: app/services/auth_service.py
Purpose: Authentication logic. ONE mode: real password auth — credentials are verified against the
    bcrypt hash in users.password_hash; users are created via register_user (hashed). The legacy
    admin/admin "stub" path was removed at the production cutover (see tasks/PLAN.md) — there is no
    longer a demo/bypass identity, and AUTH_MODE is no longer a config value. The JWT this leads to
    is verified for real on every request by app/security.py.

    NO ROLES: every account is a self-owned island (one owner, who owns all of their cases AND
    courts). The old §13 first-login admin bootstrap was removed with the roles model (migration
    0009) — there is nothing to promote and no privileged identity to obtain.
Depends on: fastapi, sqlalchemy, app/models/user.py, app/security_password.py
Related: app/api/auth.py, app/security.py, app/security_password.py, frontend /courts
Security notes: Never log passwords. Login is a bcrypt verify against a stored hash; a user with a
    NULL password_hash (none exist post-cutover) can never authenticate (verify_password returns
    False on a NULL hash).
"""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.models.user import User
from app.security_password import hash_password, verify_password

_INVALID = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password."
)


def authenticate(db: DbSession, email: str, password: str) -> User:
    """Validate credentials (bcrypt) and return the user, or raise 401. The login form's `username`
    field carries the email (auth is email-based)."""
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
    """Create a user with a hashed password. Rejects a duplicate email."""
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
