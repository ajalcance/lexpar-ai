"""
File: agents/backend_client.py
Purpose: Thin HTTP client the worker uses to talk to the backend over the scoped agent service
    token (X-Agent-Token), not a user login: read the case context at room join, and at session end
    complete the session and write the scorecard + transcript batch (Gap 4).
Depends on: httpx, agents/config.py
Related: backend/app/api/internal.py, agents/scorecard_builder.py, agents/main.py
Security notes: Sends the AGENT_SERVICE_TOKEN header over the configured backend URL only; never
    log the token or the transcript payload. Treats 409 as already-done (idempotent retries).
"""

from __future__ import annotations

import uuid

import httpx

import config

_TIMEOUT = 15.0


def is_valid_session_id(session_id: str) -> bool:
    """True if `session_id` is a real session UUID. The worker derives the id from the room name
    ('session-<uuid>'); rooms that don't match (scratch/test rooms, 'user-<id>' rooms) would only
    produce 422s from every backend call — the worker no-ops for them instead."""
    try:
        uuid.UUID(session_id)
        return True
    except ValueError:
        return False


def _headers() -> dict[str, str]:
    return {"X-Agent-Token": config.AGENT_SERVICE_TOKEN}


def get_session_context(session_id: str) -> dict:
    """Fetch the session's case facts to seed SessionState. Raises on error; the caller handles."""
    resp = httpx.get(
        f"{config.AGENT_BACKEND_URL}/api/sessions/{session_id}/context",
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def complete_session(session_id: str) -> None:
    """Mark the session completed. A 409 (already completed) is treated as success."""
    resp = httpx.post(
        f"{config.AGENT_BACKEND_URL}/api/sessions/{session_id}/complete",
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    if resp.status_code != httpx.codes.CONFLICT:
        resp.raise_for_status()


def write_scorecard(session_id: str, payload: dict) -> None:
    """Persist the scorecard + transcript batch. A 409 (already written) is treated as success."""
    resp = httpx.post(
        f"{config.AGENT_BACKEND_URL}/api/sessions/{session_id}/scorecard",
        headers=_headers(),
        json=payload,
        timeout=_TIMEOUT,
    )
    if resp.status_code != httpx.codes.CONFLICT:
        resp.raise_for_status()
