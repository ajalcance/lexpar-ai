"""
File: app/schemas/auth.py
Purpose: Pydantic shapes for the auth boundary — login request, token response, and the safe
    public view of a user (no password hash).
Depends on: pydantic
Related: app/api/auth.py, app/services/auth_service.py, app/models/user.py
Security notes: UserOut deliberately omits password_hash. Never widen it to expose secrets.
"""

import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.limits import LINE_MAX

# Email max per RFC 5321; password max bounds the bcrypt input (huge inputs are a hashing-cost DoS).
_EMAIL_MAX = 254
_PASSWORD_MAX = 128


class LoginRequest(BaseModel):
    username: str = Field(max_length=_EMAIL_MAX)
    password: str = Field(max_length=_PASSWORD_MAX)


class RegisterRequest(BaseModel):
    email: str = Field(max_length=_EMAIL_MAX)
    # basic strength floor; enforce more in production. Max bounds the bcrypt input.
    password: str = Field(min_length=8, max_length=_PASSWORD_MAX)
    full_name: str | None = Field(default=None, max_length=LINE_MAX)
    firm_name: str | None = Field(default=None, max_length=LINE_MAX)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str | None = None
    firm_name: str | None = None
    # 'attorney' | 'admin' (§13) — lets the frontend role-gate the admin UI (defense in depth;
    # the backend admin dependency remains the real enforcement).
    role: str = "attorney"
