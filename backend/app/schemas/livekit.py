"""
File: app/schemas/livekit.py
Purpose: Pydantic response shape for an issued LiveKit room access token.
Depends on: pydantic
Related: app/api/livekit_token.py, app/services/livekit_service.py
Security notes: The token grants room access — the client receives it over HTTPS and holds it
    in memory only; never log it.
"""

from pydantic import BaseModel


class LiveKitTokenOut(BaseModel):
    url: str
    token: str
