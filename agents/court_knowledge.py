"""
File: agents/court_knowledge.py
Purpose: Agent-side access to the court-rules corpus (ARCHITECTURE §13) — retrieve the VERBATIM
    procedural-rule passages of the session's forum that are relevant to the statement being
    evaluated, and render them as their own clearly-separated prompt block (RELEVANT PROCEDURAL
    RULES:, distinct from the pleading's RELEVANT PLEADING EXCERPTS: block so the model can tell
    generally-applicable rule from case-specific fact). Also `dual_blocks`, the one shared helper
    that fetches BOTH corpora in parallel for the consumers that need both (Opposing Counsel's
    reply, the Judge's rulings). Retrieval is bounded and best-effort: any failure returns no
    passages — an empty block, never a blocked live loop.
Depends on: httpx, concurrent.futures (stdlib); agents/config.py, agents/case_knowledge.py
Related: backend/app/api/internal.py (GET /sessions/{id}/court-rules), agents/judge.py,
    agents/opposing_counsel.py, agents/objection_classifier.py
Security notes: Sends only the query text over the scoped agent token. Rule passages are public
    law; the query text can carry live speech (work product) — never logged.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

import httpx

import case_knowledge
import config

logger = logging.getLogger("lexpar.agents.knowledge")

_TIMEOUT = 8.0
# The classifier's tier-3 call sits in the live barge-in path — its retrieval budget is far
# tighter than the reply/assessment paths' (a slow fetch must not stall an objection decision).
FAST_TIMEOUT = 2.0


def retrieve_court_passages(
    session_id: str, query: str, k: int = 4, timeout: float = _TIMEOUT
) -> list[str]:
    """Top-k verbatim rule passages for the session's forum. Returns [] on any error/timeout or
    when the case names no court (fail-open — the prompt simply carries no rules block)."""
    if not session_id or not query.strip():
        return []
    try:
        resp = httpx.get(
            f"{config.AGENT_BACKEND_URL}/api/sessions/{session_id}/court-rules",
            params={"q": query, "k": k},
            headers={"X-Agent-Token": config.AGENT_SERVICE_TOKEN},
            timeout=timeout,
        )
        resp.raise_for_status()
        return list(resp.json().get("passages", []))
    except Exception:
        logger.warning("court-rules retrieval unavailable — proceeding without a rules block")
        return []


def rules_block(passages: list[str]) -> str:
    """Render rule passages as their own prompt block, or '' when there are none."""
    if not passages:
        return ""
    joined = "\n\n".join(f"- {p}" for p in passages)
    return f"RELEVANT PROCEDURAL RULES:\n{joined}"


def dual_blocks(
    session_id: str, query: str, *, k: int = 4, timeout: float = _TIMEOUT
) -> tuple[str, str]:
    """Fetch pleading excerpts AND court rules for one query, in parallel (two independent
    backend calls — serializing them would double the latency cost on the live paths). Returns
    (pleading_block, rules_block), each '' when nothing was retrieved."""
    if not session_id or not query.strip():
        return "", ""
    with ThreadPoolExecutor(max_workers=2) as pool:
        case_future = pool.submit(
            case_knowledge.retrieve_passages, session_id, query, k, timeout
        )
        court_future = pool.submit(retrieve_court_passages, session_id, query, k, timeout)
        case_passages = case_future.result()
        court_passages = court_future.result()
    return case_knowledge.passages_block(case_passages), rules_block(court_passages)
