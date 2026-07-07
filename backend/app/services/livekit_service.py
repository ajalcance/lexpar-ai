"""
File: app/services/livekit_service.py
Purpose: Mint LiveKit room access tokens. A LiveKit token is a JWT signed with the LiveKit API
    secret carrying a "video" grant; we build it directly (no extra SDK) so GET /api/livekit/token
    is fully functional the moment the frontend connects.
Depends on: PyJWT, app/config.py
Related: app/api/livekit_token.py, agents/main.py (the worker joins the same room),
    docs/ARCHITECTURE.md §6
Security notes: Signs with LIVEKIT_API_SECRET (env only). Scope the grant to a single room and a
    short TTL; never log the minted token.
"""

import time

import jwt

from app.config import get_settings

DEFAULT_TTL_SECONDS = 3600


def mint_access_token(identity: str, room: str, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> str:
    """Return a signed LiveKit access token granting join access to a single room."""
    settings = get_settings()
    now = int(time.time())
    payload = {
        "iss": settings.livekit_api_key,
        "sub": identity,
        "name": identity,
        "nbf": now,
        "iat": now,
        "exp": now + ttl_seconds,
        "video": {
            "room": room,
            "roomJoin": True,
            "canPublish": True,
            "canSubscribe": True,
        },
    }
    return jwt.encode(payload, settings.livekit_api_secret, algorithm="HS256")
