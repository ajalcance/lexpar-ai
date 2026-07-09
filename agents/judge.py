"""
File: agents/judge.py
Purpose: The Judge agent. Loads its persona prompt from prompts/judge.md, assembles the session
    context (case facts + established facts + objection ledger) from SessionState, and generates
    judicial output. Two entry points, both structured JSON so the text comes back clean:
    generate_ruling (a single spoken ruling, used mid-session/harness) and assess_session (the
    end-of-session pass — rules on every pending objection, extracts the facts the attorney
    established, and gives a closing ruling, all in one call so the scorecard reflects what actually
    happened). Message assembly + parsing are pure; only the *_ruling / assess_session calls hit the
    API.
Depends on: json; agents/llm_router.py, agents/session_state.py, prompts/judge.md
Related: agents/opposing_counsel.py, agents/main.py, agents/scorecard_builder.py,
    backend/app/models/scorecard.py, docs/ARCHITECTURE.md §6 / §6.5 / §7
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

_VALID_RULINGS = ("sustained", "overruled")
_FALLBACK_CLOSING = "The court has considered the arguments. That concludes this session."

_ASSESSMENT_INSTRUCTION = (
    "Review the full session below. Then, as the presiding judge:\n"
    "1. For EACH pending objection in the SESSION RECORD, in the order listed, rule 'sustained' or "
    "'overruled' based on what the transcript shows.\n"
    "2. List 2-5 key facts the attorney genuinely established on the record (supported by the "
    "transcript and not undercut by a sustained objection). Omit if none.\n"
    "3. Give a one- to two-sentence closing ruling from the bench.\n"
    'Respond ONLY with JSON: {"rulings": ["sustained"|"overruled", ...], "established_facts": '
    '["<fact>", ...], "closing_ruling": "<what you say aloud>"}. The rulings array must have '
    "exactly one entry per pending objection, in the same order."
)

_SPEAKER_LABELS = {
    "attorney": "ATTORNEY",
    "opposing_counsel": "OPPOSING COUNSEL",
    "judge": "JUDGE",
}


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


def _render_transcript(state: SessionState) -> str:
    """A readable transcript of the session for the end-of-session assessment. Pure."""
    lines = [
        f"{_SPEAKER_LABELS.get(turn.speaker, turn.speaker.upper())}: {turn.content}"
        for turn in state.transcript
    ]
    return "\n".join(lines) or "(no transcript)"


def _build_assessment_messages(state: SessionState) -> list[dict[str, str]]:
    """Assemble the end-of-session assessment messages (persona + record + transcript). Pure."""
    context = (
        f"SESSION RECORD:\n{state.snapshot()}\n\nFULL TRANSCRIPT:\n{_render_transcript(state)}"
    )
    return [
        {"role": "system", "content": load_prompt()},
        {"role": "system", "content": context},
        {"role": "user", "content": _ASSESSMENT_INSTRUCTION},
    ]


def _parse_assessment(content: str) -> dict:
    """Parse the assessment JSON into {rulings, established_facts, closing_ruling}. Pure —
    raises on non-JSON; normalizes each ruling to sustained/overruled (unknown → overruled)."""
    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("judge did not return a JSON object")
    data = json.loads(content[start : end + 1])

    raw_rulings = data.get("rulings", [])
    rulings: list[str] = []
    if isinstance(raw_rulings, list):
        for item in raw_rulings:
            normalized = str(item).strip().lower()
            rulings.append(normalized if normalized in _VALID_RULINGS else "overruled")

    raw_facts = data.get("established_facts", [])
    facts = (
        [str(f).strip() for f in raw_facts if str(f).strip()]
        if isinstance(raw_facts, list)
        else []
    )
    closing = str(data.get("closing_ruling", "")).strip()
    return {"rulings": rulings, "established_facts": facts, "closing_ruling": closing}


def assess_session(state: SessionState) -> dict:
    """
    End-of-session pass: rule on every pending objection, extract established facts, and give a
    closing ruling — one live API call. Fails safe: on any error/unparseable output, returns no
    rulings (objections stay pending = not sustained, so the attorney is never penalized on a
    model failure), no facts, and a neutral closing ruling.
    """
    endpoint = build_endpoint(judge_config())
    try:
        content = chat(
            endpoint,
            _build_assessment_messages(state),
            temperature=0.3,
            # gpt-oss reasons before emitting; the assessment (rule every objection + extract facts
            # + closing ruling) needs a bigger budget than the classifier's 512, else the hidden
            # reasoning eats it all and content is empty (docs/LESSONS.md empty-content bug).
            max_tokens=1536,
            response_format={"type": "json_object"},
        )
        result = _parse_assessment(content)
    except Exception:
        return {"rulings": [], "established_facts": [], "closing_ruling": _FALLBACK_CLOSING}
    if not result["closing_ruling"]:
        result["closing_ruling"] = _FALLBACK_CLOSING
    return result
