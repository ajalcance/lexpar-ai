"""
File: app/api/livekit_token.py
Purpose: Route — GET /api/livekit/token issues a LiveKit room access token for the frontend to
    join a session's real-time audio room.
Depends on: fastapi, app/services/livekit_service.py, app/security.py, app/schemas/livekit.py
Related: docs/ARCHITECTURE.md §5/§6, frontend lib/livekit.ts
Security notes: Requires a bearer token; the token identity is the current user and the grant is
    scoped to a single room. Served over HTTPS in production.
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DbSession

from app.config import get_settings
from app.db import get_db
from app.models.user import User
from app.schemas.livekit import LiveKitTokenOut
from app.security import get_current_user
from app.services import livekit_service, session_service

router = APIRouter(prefix="/api/livekit", tags=["livekit"])


@router.get("/token", response_model=LiveKitTokenOut)
def get_token(
    session_id: uuid.UUID | None = None,
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> LiveKitTokenOut:
    settings = get_settings()
    if session_id is not None:
        # Validates ownership/existence and pins the token to this session's room.
        session = session_service.get_session(db, current_user, session_id)
        room = f"session-{session.id}"
    else:
        room = f"user-{current_user.id}"
    token = livekit_service.mint_access_token(identity=str(current_user.id), room=room)
    return LiveKitTokenOut(url=settings.livekit_url, token=token)
