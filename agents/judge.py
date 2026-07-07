"""
File: agents/judge.py
Purpose: The Judge agent. Loads its persona prompt from prompts/judge.md, assembles the session
    context (case facts + established facts + objection ledger) from SessionState, and generates a
    short judicial response — a ruling on a pending objection or brief guidance. Uses structured
    JSON output ({"ruling": ...}) so the spoken text comes back clean and non-empty (see §7 note on
    model choice). Message assembly + parsing are pure; only generate_ruling makes a live API call.
Depends on: json; agents/llm_router.py, agents/session_state.py, prompts/judge.md
Related: agents/opposing_counsel.py, agents/main.py, backend/app/models/scorecard.py,
    docs/ARCHITECTURE.md §6 / §7
Security notes: Feeds session content (work product) to the model as prompt context — never log it;
    it goes only to the configured endpoint.
"""

from __future__ import annotations

import json
from pathlib import Path

from llm_router import build_endpoint, chat, judge_config
from session_state import SessionState

_PROMPT_PATH = Path(__file__).parent / "prompts" / "judge.md"

_RULING_INSTRUCTION = 'Respond ONLY with JSON: {"ruling": "<what you say aloud from the bench>"}.'


def load_prompt() -> str:
    """Read the Judge persona prompt."""
    return _PROMPT_PATH.read_text(encoding="utf-8")


def build_messages(state: SessionState, attorney_turn: str) -> list[dict[str, str]]:
    """Assemble the chat messages (persona + session record + the attorney's latest turn)."""
    context = f"SESSION RECORD:\n{state.snapshot()}"
    user = (
        f'The attorney just argued:\n"{attorney_turn}"\n\n'
        "As the presiding judge, rule on any pending objection or give brief guidance if "
        f"warranted, in a sentence or two. {_RULING_INSTRUCTION}"
    )
    return [
        {"role": "system", "content": load_prompt()},
        {"role": "system", "content": context},
        {"role": "user", "content": user},
    ]


def _parse_ruling(content: str) -> str:
    """Extract the spoken ruling from the model's JSON reply. Pure — no API call."""
    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("judge did not return a JSON object")
    ruling = json.loads(content[start : end + 1]).get("ruling", "")
    return str(ruling).strip()


def generate_ruling(state: SessionState, attorney_turn: str) -> str:
    """Generate the Judge's short spoken ruling. Makes a live API call."""
    endpoint = build_endpoint(judge_config())
    content = chat(
        endpoint,
        build_messages(state, attorney_turn),
        temperature=0.3,
        max_tokens=400,
        response_format={"type": "json_object"},
    )
    return _parse_ruling(content)
