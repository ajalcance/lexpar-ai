"""
File: agents/opposing_counsel.py
Purpose: The Opposing Counsel agent. Loads its persona prompt from prompts/opposing_counsel.md,
    assembles the session context (case facts + established facts + objection rulings) from
    SessionState, and generates the next spoken reply via the reasoning model (Fireworks today,
    self-hosted vLLM later — routed by llm_router). Two transports over the same messages:
    generate_reply (blocking, full completion) and stream_reply (yields text deltas for the
    sentence-level verification pipeline, §6.5). build_continuation_messages/stream_continuation
    are the mid-stream repair path: when a sentence fails verification, they prompt the model to
    continue from the already-spoken (verified) prefix without repeating the rejected claim.
    Message assembly is pure; only generate_reply/stream_reply/stream_continuation call the API.
Depends on: agents/llm_router.py, agents/session_state.py, prompts/opposing_counsel.md
Related: agents/verification.py (verifies the draft), agents/streaming_verify.py (the per-sentence
    pipeline), agents/main.py (voice pipeline), docs/ARCHITECTURE.md §6 / §6.5
Security notes: Feeds case facts + live transcript (work product) to the model as prompt context —
    never log that context; it goes only to the configured endpoint.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from llm_router import build_endpoint, chat, chat_stream, opposing_counsel_config
from session_state import SessionState

_PROMPT_PATH = Path(__file__).parent / "prompts" / "opposing_counsel.md"

_REPLY_STYLE = (
    "Respond as opposing counsel in a few spoken sentences. Output only the words you say "
    "aloud in the courtroom — no analysis, headings, quotation marks, or preamble."
)


def load_prompt() -> str:
    """Read the Opposing Counsel persona prompt."""
    return _PROMPT_PATH.read_text(encoding="utf-8")


def build_messages(
    state: SessionState, attorney_turn: str, excerpts: str = ""
) -> list[dict[str, str]]:
    """Assemble the chat messages (persona + session record + optional retrieved pleading excerpts
    + the attorney's latest turn). `excerpts` (§12) are the passages retrieved for this turn."""
    context = f"SESSION RECORD (what is on the record so far):\n{state.snapshot()}"
    if excerpts:
        context += f"\n\n{excerpts}"
    user = f'The attorney just argued:\n"{attorney_turn}"\n\n{_REPLY_STYLE}'
    return [
        {"role": "system", "content": load_prompt()},
        {"role": "system", "content": context},
        {"role": "user", "content": user},
    ]


def build_continuation_messages(
    state: SessionState, attorney_turn: str, spoken_prefix: str, failure_reason: str
) -> list[dict[str, str]]:
    """
    Assemble the mid-stream repair prompt (§6.5, Option B): a sentence failed verification after
    `spoken_prefix` was already spoken aloud, so ask the model to continue from that prefix without
    repeating the rejected claim. Pure — no API call.
    """
    context = f"SESSION RECORD (what is on the record so far):\n{state.snapshot()}"
    if spoken_prefix:
        situation = (
            f'You are mid-reply and have already said aloud: "{spoken_prefix}"\n'
            f"Your next sentence was rejected by verification: {failure_reason}\n"
            "Continue the reply from where you left off. Do not repeat what you have spoken, "
            "and do not restate the rejected claim."
        )
    else:
        situation = (
            f"Your draft reply was rejected by verification: {failure_reason}\n"
            "Respond again, avoiding the rejected claim."
        )
    user = f'The attorney just argued:\n"{attorney_turn}"\n\n{situation}\n\n{_REPLY_STYLE}'
    return [
        {"role": "system", "content": load_prompt()},
        {"role": "system", "content": context},
        {"role": "user", "content": user},
    ]


def generate_reply(state: SessionState, attorney_turn: str) -> str:
    """Generate Opposing Counsel's next reply (blocking, full completion). Makes a live API call."""
    endpoint = build_endpoint(opposing_counsel_config())
    messages = build_messages(state, attorney_turn)
    return chat(endpoint, messages, temperature=0.7, max_tokens=400).strip()


def stream_reply(
    state: SessionState, attorney_turn: str, session_id: str = ""
) -> Iterator[str]:
    """Stream Opposing Counsel's next reply as text deltas. Makes a live API call. If `session_id`
    is given, retrieves the pleading passages relevant to this turn (§12) and grounds the reply in
    them (best-effort — retrieval failure just proceeds on the case summary)."""
    excerpts = ""
    if session_id:
        import case_knowledge

        excerpts = case_knowledge.passages_block(
            case_knowledge.retrieve_passages(session_id, attorney_turn)
        )
    endpoint = build_endpoint(opposing_counsel_config())
    yield from chat_stream(
        endpoint, build_messages(state, attorney_turn, excerpts), temperature=0.7, max_tokens=400
    )


def stream_continuation(
    state: SessionState, attorney_turn: str, spoken_prefix: str, failure_reason: str
) -> Iterator[str]:
    """Stream the repair continuation after a mid-stream verification failure. Live API call."""
    endpoint = build_endpoint(opposing_counsel_config())
    messages = build_continuation_messages(state, attorney_turn, spoken_prefix, failure_reason)
    yield from chat_stream(endpoint, messages, temperature=0.7, max_tokens=400)
