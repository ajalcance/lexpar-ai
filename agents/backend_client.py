"""
File: agents/backend_client.py
Purpose: Thin HTTP client the worker uses at session end to persist to the backend (Gap 4) —
    complete the session and write the scorecard + transcript batch — authenticating with the
    scoped agent service token (X-Agent-Token), not a user login.
Depends on: httpx, agents/config.py
Related: backend/app/api/internal.py, agents/scorecard_builder.py, agents/main.py
Security notes: Sends the AGENT_SERVICE_TOKEN header over the configured backend URL only; never
    log the token or the transcript payload. Treats 409 as already-done (idempotent retries).
"""

from __future__ import annotations

import httpx

import config

_TIMEOUT = 15.0


def _headers() -> dict[str, str]:
    return {"X-Agent-Token": config.AGENT_SERVICE_TOKEN}


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
