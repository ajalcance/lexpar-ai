"""
File: agents/scorecard_builder.py
Purpose: Derive the end-of-session scorecard payload from SessionState + the Judge's closing ruling
    (Gap 4). Pure and deterministic so it is fully offline-testable — no LLM call in the shutdown
    path. Heuristic: start at 100, −8 per sustained objection (clamped ≥ 0); strengths = the (up to
    5 most recent) established facts; weaknesses = the unique sustained-objection grounds; judge
    ruling stored verbatim.
Depends on: agents/session_state.py (no network)
Related: agents/backend_client.py (sends this), backend/app/schemas/agent.py (the matching shape)
Security notes: The payload carries transcript content (work product) — built in memory, sent only
    to the backend over the agent credential, never logged.
"""

from __future__ import annotations

from session_state import SessionState

SCORE_START = 100
SUSTAINED_PENALTY = 8
MAX_STRENGTHS = 5


def _overall_score(state: SessionState) -> int:
    return max(0, SCORE_START - SUSTAINED_PENALTY * len(state.sustained_objections()))


def _strengths(state: SessionState) -> str:
    facts = state.established_facts[-MAX_STRENGTHS:]  # up to 5 most recent (already deduped on add)
    if not facts:
        return "No facts were formally established during this session."
    return "\n".join(f"- {fact}" for fact in facts)


def _weaknesses(state: SessionState) -> str:
    unique_grounds: list[str] = []
    for objection in state.sustained_objections():
        if objection.grounds not in unique_grounds:
            unique_grounds.append(objection.grounds)
    if not unique_grounds:
        return "No objections were sustained against your argument."
    return "\n".join(f"- Sustained objection: {grounds}" for grounds in unique_grounds)


def build_transcript(state: SessionState) -> list[dict]:
    """The transcript batch, in order, shaped for the backend's TranscriptTurnIn."""
    return [
        {
            "speaker": turn.speaker,
            "content": turn.content,
            "was_interruption": turn.was_interruption,
            "spoken_at": turn.spoken_at.isoformat(),
        }
        for turn in state.transcript
    ]


def build_session_end_payload(state: SessionState, judge_ruling: str) -> dict:
    """The full POST /scorecard body: derived scorecard + the transcript batch."""
    return {
        "overall_score": _overall_score(state),
        "strengths": _strengths(state),
        "weaknesses": _weaknesses(state),
        "judge_ruling": judge_ruling,
        "transcript": build_transcript(state),
    }
