"""
File: agents/judge.py
Purpose: The Judge agent. Loads its persona prompt from prompts/judge.md, assembles the session
    context (case facts + established facts + objection ledger) from SessionState, and generates
    judicial output. Three API-calling entry points, all structured JSON so the text comes back
    clean: generate_ruling (a single spoken ruling, used mid-session/harness); quick_ruling (the
    inline sustained/overruled call the Judge speaks right after an objection barges in, §6.5); and
    assess_session (the end-of-session pass — rules on every pending objection, extracts the facts
    the attorney established, and gives a closing ruling, all in one call so the scorecard reflects
    what actually happened). Message assembly + parsing are pure; only the *_ruling / quick_ruling /
    assess_session calls hit the API.
Depends on: json; agents/llm_router.py, agents/session_state.py, prompts/judge.md
Related: agents/opposing_counsel.py, agents/main.py, agents/scorecard_builder.py,
    backend/app/models/scorecard.py, docs/ARCHITECTURE.md §6 / §6.5 / §7
Security notes: Feeds session content (work product) to the model as prompt context — never log it;
    it goes only to the configured endpoint.
"""

from __future__ import annotations

import json
from pathlib import Path

import court_knowledge
from llm_router import build_endpoint, chat, judge_config, objection_config
from session_state import Objection, SessionState

_PROMPT_PATH = Path(__file__).parent / "prompts" / "judge.md"

_RULING_INSTRUCTION = 'Respond ONLY with JSON: {"ruling": "<what you say aloud from the bench>"}.'

_VALID_RULINGS = ("sustained", "overruled")
_FALLBACK_CLOSING = "The court has considered the arguments. That concludes this session."

_ASSESSMENT_INSTRUCTION = (
    "Review the full session below. Then, as the presiding judge:\n"
    "1. For EACH objection still marked [pending] in the SESSION RECORD, in the order listed, rule "
    "'sustained' or 'overruled' based on what the transcript shows. Objections already marked "
    "[sustained] or [overruled] were ruled from the bench DURING the session — do NOT re-rule "
    "them; treat those rulings as final.\n"
    "2. List 2-5 key facts the attorney genuinely established on the record (supported by the "
    "transcript and not undercut by a sustained objection). Omit if none.\n"
    "3. Give a one- to two-sentence closing ruling from the bench that reflects the session as a "
    "whole, including a brief acknowledgment of the objections already ruled during the session.\n"
    'Respond ONLY with JSON: {"rulings": ["sustained"|"overruled", ...], "established_facts": '
    '["<fact>", ...], "closing_ruling": "<what you say aloud>"}. The rulings array must have '
    "exactly one entry per [pending] objection, in the same order (empty array if none are "
    "pending)."
)

_QUICK_RULING_SYSTEM = (
    "You are the presiding judge in a courtroom rehearsal. Opposing Counsel just objected to the "
    "attorney's in-progress statement. Rule IMMEDIATELY, as from the bench: sustained or "
    "overruled, with one short reason (a few words, spoken aloud). Respond ONLY with JSON "
    '{"ruling": "sustained"|"overruled", "reason": "<a few words>"}.'
)

_SPEAKER_LABELS = {
    "attorney": "ATTORNEY",
    "opposing_counsel": "OPPOSING COUNSEL",
    "judge": "JUDGE",
}


def load_prompt() -> str:
    """Read the Judge persona prompt."""
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _grounded_context(state: SessionState, excerpts: str, rules: str) -> str:
    """The session record plus the two clearly-separated retrieval blocks (§12 pleading excerpts,
    §13 procedural rules) — kept distinct so the model can tell case-specific fact from
    generally-applicable rule. Pure."""
    context = f"SESSION RECORD:\n{state.snapshot()}"
    if excerpts:
        context += f"\n\n{excerpts}"
    if rules:
        context += f"\n\n{rules}"
    return context


def build_messages(
    state: SessionState, attorney_turn: str, excerpts: str = "", rules: str = ""
) -> list[dict[str, str]]:
    """Assemble the chat messages (persona + grounded session record + the attorney's latest
    turn). Pure — retrieval happens in the live wrappers."""
    user = (
        f'The attorney just argued:\n"{attorney_turn}"\n\n'
        "As the presiding judge, rule on any pending objection or give brief guidance if "
        f"warranted, in a sentence or two. {_RULING_INSTRUCTION}"
    )
    return [
        {"role": "system", "content": load_prompt()},
        {"role": "system", "content": _grounded_context(state, excerpts, rules)},
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
    """Generate the Judge's short spoken ruling. Makes a live API call. When the state carries a
    session_id (live worker), the ruling is grounded in retrieved pleading excerpts + the forum's
    procedural rules (§13 — this closes the Judge's missing-RAG gap found by the audit)."""
    excerpts, rules = court_knowledge.dual_blocks(state.session_id, attorney_turn)
    endpoint = build_endpoint(judge_config())
    content = chat(
        endpoint,
        build_messages(state, attorney_turn, excerpts, rules),
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


def _build_assessment_messages(
    state: SessionState, excerpts: str = "", rules: str = ""
) -> list[dict[str, str]]:
    """Assemble the end-of-session assessment messages (persona + grounded record + transcript).
    Pure — retrieval happens in assess_session."""
    context = (
        f"{_grounded_context(state, excerpts, rules)}\n\n"
        f"FULL TRANSCRIPT:\n{_render_transcript(state)}"
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


def _build_quick_ruling_messages(
    state: SessionState,
    objection: Objection,
    fragment: str,
    excerpts: str = "",
    rules: str = "",
) -> list[dict[str, str]]:
    """Assemble the inline-ruling messages (minimal — this sits in the live path). Pure."""
    user = (
        f"{_grounded_context(state, excerpts, rules)}\n\n"
        f'ATTORNEY (statement objected to): "{fragment}"\n'
        f"OBJECTION: {objection.grounds} (raised by {objection.raised_by})"
    )
    return [
        {"role": "system", "content": _QUICK_RULING_SYSTEM},
        {"role": "user", "content": user},
    ]


def _parse_quick_ruling(content: str) -> tuple[str, str]:
    """Parse {"ruling", "reason"} → (ruling, reason). Pure — raises on non-JSON or an unknown
    ruling value (the caller fails safe: silent, objection stays pending)."""
    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("judge did not return a JSON object")
    data = json.loads(content[start : end + 1])
    ruling = str(data.get("ruling", "")).strip().lower()
    if ruling not in _VALID_RULINGS:
        raise ValueError(f"unknown ruling {ruling!r}")
    reason = str(data.get("reason", "")).strip()
    return ruling, reason


def quick_ruling(state: SessionState, objection: Objection, fragment: str) -> tuple[str, str]:
    """
    Inline ruling for a just-fired objection — the judge's real-time "Sustained/Overruled" (§6.5).
    Uses the FAST model (the objection classifier's config, gpt-oss class) because this sits
    directly in the live conversational path — same latency philosophy as the classifier and
    verification, NOT the reasoning model. Returns (ruling, reason). Raises on any error or
    unparseable output — the caller stays silent and leaves the objection pending for the
    end-of-session assessment (never fabricate a ruling).
    """
    # Targeted §13 grounding: query = the objection's grounds + the objected statement. Fetched in
    # parallel with a TIGHT budget — this call already runs concurrently with the canned objection
    # line's playback (main.py), and a slow retrieval must not push the spoken ruling late; on
    # timeout the ruling simply proceeds ungrounded-but-recorded, same fail-open as everywhere.
    excerpts, rules = court_knowledge.dual_blocks(
        state.session_id,
        f"{objection.grounds}: {fragment}",
        timeout=court_knowledge.FAST_TIMEOUT,
    )
    endpoint = build_endpoint(objection_config())
    content = chat(
        endpoint,
        _build_quick_ruling_messages(state, objection, fragment, excerpts, rules),
        temperature=0.0,
        # gpt-oss reasons before emitting; 512 was intermittently EMPTY for this prompt (the
        # session record makes it longer than the classifier's), so give it the same headroom
        # rule as assess_session: the empty-content floor scales with prompt/task complexity
        # (docs/LESSONS.md). A larger cap costs nothing when unused.
        max_tokens=1024,
        response_format={"type": "json_object"},
    )
    return _parse_quick_ruling(content)


def assess_session(state: SessionState) -> dict:
    """
    End-of-session pass: rule on every pending objection, extract established facts, and give a
    closing ruling — one live API call. Fails safe: on any error/unparseable output, returns no
    rulings (objections stay pending = not sustained, so the attorney is never penalized on a
    model failure), no facts, and a neutral closing ruling.
    """
    # §13 grounding for the assessment: what is being judged is the pending objections (plus the
    # session's closing context), so the retrieval query is their grounds + the last attorney
    # turn — targeted, not a generic dump of the whole transcript.
    pending = ", ".join(o.grounds for o in state.pending_objections())
    last_turn = next(
        (t.content for t in reversed(state.transcript) if t.speaker == "attorney"), ""
    )
    excerpts, rules = court_knowledge.dual_blocks(
        state.session_id, f"{pending} {last_turn}".strip()
    )
    endpoint = build_endpoint(judge_config())
    try:
        content = chat(
            endpoint,
            _build_assessment_messages(state, excerpts, rules),
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
