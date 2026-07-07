"""
File: agents/opposing_counsel.py
Purpose: The Opposing Counsel agent. Loads its persona prompt from prompts/opposing_counsel.md,
    assembles the session context (case facts + established facts + objection rulings) from
    SessionState, and generates the next spoken reply via the reasoning model (Fireworks today,
    self-hosted vLLM later — routed by llm_router). Message assembly is a pure function; only
    generate_reply makes a live API call.
Depends on: agents/llm_router.py, agents/session_state.py, prompts/opposing_counsel.md
Related: agents/verification.py (verifies the draft), agents/main.py (eventual voice pipeline),
    docs/ARCHITECTURE.md §6
Security notes: Feeds case facts + live transcript (work product) to the model as prompt context —
    never log that context; it goes only to the configured endpoint.
"""

from __future__ import annotations

from pathlib import Path

from llm_router import build_endpoint, chat, opposing_counsel_config
from session_state import SessionState

_PROMPT_PATH = Path(__file__).parent / "prompts" / "opposing_counsel.md"


def load_prompt() -> str:
    """Read the Opposing Counsel persona prompt."""
    return _PROMPT_PATH.read_text(encoding="utf-8")


def build_messages(state: SessionState, attorney_turn: str) -> list[dict[str, str]]:
    """Assemble the chat messages (persona + session record + the attorney's latest turn)."""
    context = f"SESSION RECORD (what is on the record so far):\n{state.snapshot()}"
    user = (
        f'The attorney just argued:\n"{attorney_turn}"\n\n'
        "Respond as opposing counsel in a few spoken sentences. Output only the words you say "
        "aloud in the courtroom — no analysis, headings, quotation marks, or preamble."
    )
    return [
        {"role": "system", "content": load_prompt()},
        {"role": "system", "content": context},
        {"role": "user", "content": user},
    ]


def generate_reply(state: SessionState, attorney_turn: str) -> str:
    """Generate Opposing Counsel's next reply. Makes a live API call."""
    endpoint = build_endpoint(opposing_counsel_config())
    messages = build_messages(state, attorney_turn)
    return chat(endpoint, messages, temperature=0.7, max_tokens=400).strip()
