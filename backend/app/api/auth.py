"""
File: app/api/auth.py
Purpose: Auth routes — POST /api/auth/login (issue a JWT) and GET /api/auth/me (current user).
Depends on: fastapi, app/services/auth_service.py, app/security.py, app/schemas/auth.py
Related: docs/ARCHITECTURE.md §5, frontend Login.tsx
Security notes: /login is the only unauthenticated route here; /me requires a valid bearer token.
    Never log request bodies (they carry credentials).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DbSession

from app.config import get_settings
from app.db import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserOut
from app.security import create_access_token, get_current_user
from app.services import auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(payload: RegisterRequest, db: DbSession = Depends(get_db)) -> TokenResponse:
    # Real self-service signup (production auth). Disabled under the demo stub so the two paths
    # can't be mixed. Returns a token so the client is logged in immediately.
    if get_settings().auth_mode == "stub":
        raise HTTPException(status_code=404, detail="Registration is disabled in demo (stub) mode.")
    user = auth_service.register_user(
        db, payload.email, payload.password, payload.full_name, payload.firm_name
    )
    return TokenResponse(access_token=create_access_token(str(user.id)))


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: DbSession = Depends(get_db)) -> TokenResponse:
    user = auth_service.authenticate(db, payload.username, payload.password)
    return TokenResponse(access_token=create_access_token(str(user.id)))


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
