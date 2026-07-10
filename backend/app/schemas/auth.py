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


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=8)  # basic strength floor; enforce more in production
    full_name: str | None = None
    firm_name: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str | None = None
    firm_name: str | None = None
