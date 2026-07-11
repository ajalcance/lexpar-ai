"""
File: app/services/auth_service.py
Purpose: Authentication logic. ONE mode: real password auth — credentials are verified against the
    bcrypt hash in users.password_hash; users are created via register_user (hashed). The legacy
    admin/admin "stub" path was removed at the production cutover (see tasks/PLAN.md) — there is no
    longer a demo/bypass identity, and AUTH_MODE is no longer a config value. The JWT this leads to
    is verified for real on every request by app/security.py.

    ADMIN BOOTSTRAP (§13): the FIRST user to authenticate on a deployment with no active admin is
    promoted to admin automatically (ensure_admin_bootstrap, called from login and from register,
    which returns a token and is therefore also a first login). This makes Court/rule setup a
    pure-UI workflow — no script or CLI is ever needed to obtain admin access.
    Race-safety reasoning (documented per the §13 bootstrap task):
    - Chosen: a SINGLE atomic conditional UPDATE — "promote this user IF no active admin exists"
      as one statement (aliased NOT-EXISTS guard), so there is no ORM-level check-then-act window.
      Per-statement atomicity holds on both SQLite (single writer) and Postgres.
    - Residual: under Postgres READ COMMITTED, two truly simultaneous first-logins-EVER (fresh,
      admin-less deployment, same instant) could each evaluate the guard before either commits and
      both be promoted. That failure mode is benign — two founding users of an empty install both
      become admin; admins hold no privileges against each other and roles can be corrected in the
      DB.
    - Upgrade path if it ever matters: take a pg advisory lock (or SERIALIZABLE) around the
      bootstrap statement. Deliberately not done now — disproportionate to the risk.
Depends on: fastapi, sqlalchemy, app/models/user.py, app/security_password.py
Related: app/api/auth.py, app/security.py, app/security_password.py, frontend /admin (Phase 6)
Security notes: Never log passwords. Login is a bcrypt verify against a stored hash; a user with a
    NULL password_hash (none exist post-cutover) can never authenticate (verify_password returns
    False on a NULL hash). The bootstrap can only ever promote on an ADMIN-LESS deployment — once
    any active admin exists, no login can escalate anyone.
"""

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import aliased

from app.models.user import User
from app.security_password import hash_password, verify_password

_INVALID = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password."
)


def authenticate(db: DbSession, email: str, password: str) -> User:
    """Validate credentials (bcrypt) and return the user, or raise 401. Every successful login
    passes through the admin bootstrap (first user on an admin-less deployment → admin). The login
    form's `username` field carries the email (auth is email-based)."""
    user = _authenticate_production(db, email, password)
    return ensure_admin_bootstrap(db, user)


def ensure_admin_bootstrap(db: DbSession, user: User) -> User:
    """Promote `user` to admin IFF the deployment has no active admin (§13 UI-native bootstrap).
    One atomic conditional UPDATE — see the file header for the race-safety reasoning. Idempotent
    and a no-op the moment any active (non-soft-deleted) admin exists."""
    if user.role == "admin":
        return user
    other = aliased(User)
    no_active_admin = ~(
        select(other.id)
        .where(other.role == "admin", other.deleted_at.is_(None))
        .exists()
    )
    result = db.execute(
        update(User).where(User.id == user.id, no_active_admin).values(role="admin")
    )
    db.commit()
    db.refresh(user)
    if result.rowcount:
        # Identifier-only log (never credentials): the audit trail for how this admin came to be.
        import logging

        logging.getLogger("lexpar").info(
            "admin bootstrap: first login promoted user %s to admin", user.id
        )
    return user


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
    # Register returns a token (the client is logged in immediately), so it IS a first login —
    # the first registrant on a fresh, admin-less deployment becomes the admin.
    return ensure_admin_bootstrap(db, user)
