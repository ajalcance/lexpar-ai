"""
File: agents/case_knowledge.py
Purpose: Agent-side access to the Case Knowledge Base (ARCHITECTURE §12). The structured pleading
    summary is loaded once at room join into SessionState.case_summary (in every prompt via
    snapshot()); this module additionally retrieves the specific pleading passages most relevant to
    the attorney's current statement, so Opposing Counsel objects and the Judge rules with the
    receipts, not just the digest. Retrieval is a bounded, best-effort backend call — on any failure
    it returns no passages (the summary still grounds the reasoning), never blocking the live loop.
Depends on: httpx, agents/config.py
Related: backend/app/api/internal.py (GET /sessions/{id}/knowledge), agents/opposing_counsel.py,
    agents/judge.py
Security notes: Sends only the query text over the scoped agent token; never logs the pleading text.
"""

from __future__ import annotations

import logging

import httpx

import config

logger = logging.getLogger("lexpar.agents.knowledge")

_TIMEOUT = 8.0


def retrieve_passage_refs(
    session_id: str, query: str, k: int = 4, timeout: float = _TIMEOUT
) -> tuple[list[str], list[str]]:
    """Top-k relevant pleading passages for `query`, plus the parallel chunk ids that produced
    them (§13 provenance). Returns ([], []) on any error/timeout (fail-open — the case summary in
    the prompt still grounds the reply). `timeout` lets latency-sensitive callers (§13 dual
    retrieval on live paths) use a tighter budget than the default."""
    if not session_id or not query.strip():
        return [], []
    try:
        resp = httpx.get(
            f"{config.AGENT_BACKEND_URL}/api/sessions/{session_id}/knowledge",
            params={"q": query, "k": k},
            headers={"X-Agent-Token": config.AGENT_SERVICE_TOKEN},
            timeout=timeout,
        )
        resp.raise_for_status()
        body = resp.json()
        return list(body.get("passages", [])), list(body.get("chunk_ids", []))
    except Exception:
        logger.warning("case-knowledge retrieval unavailable — proceeding on the summary alone")
        return [], []


def retrieve_passages(
    session_id: str, query: str, k: int = 4, timeout: float = _TIMEOUT
) -> list[str]:
    """The passage texts only (see retrieve_passage_refs for the id-carrying variant)."""
    passages, _chunk_ids = retrieve_passage_refs(session_id, query, k, timeout)
    return passages


def passages_block(passages: list[str]) -> str:
    """Render retrieved passages as a prompt block, or '' when there are none."""
    if not passages:
        return ""
    joined = "\n\n".join(f"- {p}" for p in passages)
    return f"RELEVANT PLEADING EXCERPTS:\n{joined}"
