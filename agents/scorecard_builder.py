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

from dataclasses import replace

from session_state import SessionState, TranscriptTurn

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


def coalesce_transcript(turns: list[TranscriptTurn]) -> list[TranscriptTurn]:
    """Turn the raw captured turns into a clean, readable RECORD for the report:
      1. ORDER by when each turn was actually spoken (spoken_at). Objections and rulings are
         recorded the instant they fire — mid-utterance, on an interim — while an attorney turn is
         committed at turn-end; ordering by spoken_at (attorney turns are timestamped at their
         START, see main.on_user_turn_completed) puts the objection/ruling AFTER the statement it
         responds to, not before it.
      2. MERGE consecutive fragments of continuous speech from the same speaker into one turn — STT
         + turn detection split one spoken stretch into several ("You" / "Your honor…"). Discrete
         barge-ins (was_interruption) are never merged: each objection stays its own line.
    Pure; operates on copies so `state.transcript` is untouched (it stays the raw capture)."""
    ordered = sorted(turns, key=lambda t: t.spoken_at)
    merged: list[TranscriptTurn] = []
    for turn in ordered:
        prev = merged[-1] if merged else None
        can_merge = (
            prev is not None
            and prev.speaker == turn.speaker
            and not prev.was_interruption
            and not turn.was_interruption
        )
        if can_merge:
            prev.content = f"{prev.content} {turn.content}".strip()
        else:
            merged.append(replace(turn))
    return merged


def build_transcript(state: SessionState) -> list[dict]:
    """The transcript batch for the report — ordered + fragment-merged (coalesce_transcript),
    shaped for the backend's TranscriptTurnIn."""
    return [
        {
            "speaker": turn.speaker,
            "content": turn.content,
            "was_interruption": turn.was_interruption,
            "spoken_at": turn.spoken_at.isoformat(),
        }
        for turn in coalesce_transcript(state.transcript)
    ]


def build_session_end_payload(
    state: SessionState,
    judge_ruling: str,
    performance_score: int | None = None,
    performance_notes: list[str] | None = None,
) -> dict:
    """The full POST /scorecard body: derived scorecard + the transcript batch.

    `performance_score`/`performance_notes` come from the judge's end-of-session rubric
    (assess_session item 4 — command of the record, responsiveness to rulings, argument
    structure, procedural discipline). When present, the judge's grade IS the score and the notes
    join the weaknesses — otherwise (model failure, older worker) the original deterministic
    heuristic stands unchanged, so the scorecard can never come back empty or fabricated. This
    fixes the hollow "always 100 / no weaknesses" scorecard: sustained objections are rarer now
    that the bench rules on the merits, so they alone no longer measure the performance."""
    score = performance_score if performance_score is not None else _overall_score(state)
    weaknesses = _weaknesses(state)
    if performance_notes:
        observed = "\n".join(f"- {note}" for note in performance_notes)
        no_sustained = not state.sustained_objections()
        weaknesses = observed if no_sustained else f"{weaknesses}\n{observed}"
    return {
        "overall_score": score,
        "strengths": _strengths(state),
        "weaknesses": weaknesses,
        "judge_ruling": judge_ruling,
        "transcript": build_transcript(state),
    }
