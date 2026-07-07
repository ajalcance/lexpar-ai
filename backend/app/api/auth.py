"""
File: app/api/auth.py
Purpose: Auth routes — POST /api/auth/login (issue a JWT) and GET /api/auth/me (current user).
Depends on: fastapi, app/services/auth_service.py, app/security.py, app/schemas/auth.py
Related: docs/ARCHITECTURE.md §5, frontend Login.tsx
Security notes: /login is the only unauthenticated route here; /me requires a valid bearer token.
    Never log request bodies (they carry credentials).
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DbSession

from app.db import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenResponse, UserOut
from app.security import create_access_token, get_current_user
from app.services import auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: DbSession = Depends(get_db)) -> TokenResponse:
    user = auth_service.authenticate(db, payload.username, payload.password)
    return TokenResponse(access_token=create_access_token(str(user.id)))


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
