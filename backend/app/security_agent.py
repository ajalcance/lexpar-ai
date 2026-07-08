"""
File: app/security_agent.py
Purpose: A scoped service credential for the agents worker — DISTINCT from user JWT auth
    (app/security.py). It validates a static token in the `X-Agent-Token` header and is applied
    ONLY to the internal session-write routes (least privilege, DEV_GUIDELINES §7). It loads no
    user and grants nothing on the user-facing routes.
Depends on: fastapi, app/config.py
Related: app/api/internal.py, app/security.py (the separate user mechanism), docs/ARCHITECTURE.md §5
Security notes: The token comes from AGENT_SERVICE_TOKEN (env only). Compared in constant time.
    If unset, every internal call is rejected (fail closed). Never log the token.
"""

import secrets

from fastapi import Header, HTTPException, status

from app.config import get_settings


def require_agent_service(x_agent_token: str | None = Header(default=None)) -> None:
    """Allow the request only if X-Agent-Token matches the configured agent service token."""
    configured = get_settings().agent_service_token
    if not configured or not x_agent_token or not secrets.compare_digest(x_agent_token, configured):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing agent service token.",
        )
