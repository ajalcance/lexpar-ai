"""
File: app/security.py
Purpose: Bearer-token security — mint and verify JWTs and provide the get_current_user
    dependency every protected route depends on. The auth *check* here is real even though the
    auth *provider* is stubbed (ARCHITECTURE §4/§11): a missing or invalid token is always
    rejected with 401.
Depends on: PyJWT, fastapi, sqlalchemy, app/config.py, app/db.py, app/models/user.py
Related: app/services/auth_service.py, app/api/auth.py
Security notes: Tokens are signed with JWT_SECRET (env only). Never log token contents.
"""

import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session as DbSession

from app.config import get_settings
from app.db import get_db
from app.models.user import User

_settings = get_settings()
_bearer = HTTPBearer(auto_error=False)


def create_access_token(subject: str) -> str:
    """Sign a short-lived JWT whose subject is the user id."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + timedelta(minutes=_settings.access_token_ttl_minutes),
    }
    return jwt.encode(payload, _settings.jwt_secret, algorithm=_settings.jwt_algorithm)


def _credentials_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: DbSession = Depends(get_db),
) -> User:
    """Resolve the authenticated user from the bearer token, or raise 401."""
    if credentials is None or not credentials.credentials:
        raise _credentials_exception()
    try:
        payload = jwt.decode(
            credentials.credentials, _settings.jwt_secret, algorithms=[_settings.jwt_algorithm]
        )
    except jwt.PyJWTError:
        raise _credentials_exception() from None

    subject = payload.get("sub")
    if not subject:
        raise _credentials_exception()
    try:
        user_id = uuid.UUID(str(subject))
    except ValueError:
        raise _credentials_exception() from None

    user = db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise _credentials_exception()
    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """403 unless the authenticated user has the admin role — gates the court/rule-corpus
    management routes (§13). Composes get_current_user, so an invalid token still 401s; a valid
    non-admin token 403s (authenticated, not authorized). This is USER authorization — distinct
    from the agent service credential (app/security_agent.py), which is service-to-service."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator role required.",
        )
    return current_user


def require_destructive_actions_enabled() -> None:
    """Gate archive/purge routes: 403 when DESTRUCTIVE_ACTIONS_ENABLED=false (a
    public/shared-credential deployment, e.g. the hackathon demo) so nobody can delete or hide the
    demo data. Reads settings at call time so it's togglable per deployment and in tests. Default
    enabled — local dev and tests are unaffected."""
    if not get_settings().destructive_actions_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Archiving and purging are temporarily disabled on this deployment.",
        )
