"""
File: agents/judge.py
Purpose: The Judge agent. Loads its persona + sub-task prompts through the registry (prompts.render
    — judge, judge_ruling_instruction, judge_assessment, judge_quick_ruling), assembles the session
    context (case facts + established facts + objection ledger) from SessionState, and generates
    judicial output. Three API-calling entry points, all structured JSON so the text comes back
    clean: generate_ruling (a single spoken ruling, used mid-session/harness); quick_ruling (the
    inline sustained/overruled call the Judge speaks right after an objection barges in, §6.5); and
    assess_session (the end-of-session pass — rules on every pending objection, extracts the facts
    the attorney established, and gives a closing ruling, all in one call so the scorecard reflects
    what actually happened). Message assembly + parsing are pure; only the *_ruling / quick_ruling /
    assess_session calls hit the API.
Depends on: json; agents/prompts.py (prompt registry), agents/llm_router.py, agents/session_state.py
Related: agents/opposing_counsel.py, agents/main.py, agents/scorecard_builder.py,
    backend/app/models/scorecard.py, docs/ARCHITECTURE.md §6 / §6.5 / §7
Security notes: Feeds session content (work product) to the model as prompt context — never log it;
    it goes only to the configured endpoint.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

import audio_tags
import citation_check
import court_knowledge
import prompts
from llm_router import build_endpoint, chat, judge_config, objection_config
from session_state import Objection, SessionState

logger = logging.getLogger("lexpar.agents.judge")

_VALID_RULINGS = ("sustained", "overruled")
_FALLBACK_CLOSING = "The court has considered the arguments. That concludes this session."

_SPEAKER_LABELS = {
    "attorney": "ATTORNEY",
    "opposing_counsel": "OPPOSING COUNSEL",
    "judge": "JUDGE",
}


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
        f'warranted, in a sentence or two. {prompts.render("judge_ruling_instruction")}'
    )
    return [
        {"role": "system", "content": prompts.render("judge")},
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
    retrieval = court_knowledge.dual_retrieval(state.session_id, attorney_turn)
    endpoint = build_endpoint(judge_config())
    content = chat(
        endpoint,
        build_messages(state, attorney_turn, *retrieval.blocks()),
        temperature=0.3,
        max_tokens=400,
        response_format={"type": "json_object"},
    )
    ruling = _parse_ruling(content)
    # §13 Phase 5: flag-and-log only on this (harness/legacy) path — the live paths persist
    # provenance rows; this one is not wired into the worker.
    flagged = citation_check.flag_ungrounded(ruling, retrieval.shown_text)
    if flagged:
        logger.warning(
            "ungrounded citation(s) in ruling [session=%s path=generate_ruling citations=%s "
            "flagged=true]",
            state.session_id,
            flagged,
        )
    return ruling


# Char cap for the assessment transcript (~4k tokens). Uncapped, a long session's FULL TRANSCRIPT
# could blow the judge's context exactly when it matters most (the closing ruling + scorecard).
# The most recent turns are kept — they carry the pending objections being ruled — and the durable
# record (facts + ledger) is always fully present via _grounded_context regardless of this cap.
_TRANSCRIPT_MAX_CHARS = 16000


def _render_transcript(state: SessionState) -> str:
    """A readable transcript for the end-of-session assessment, capped at _TRANSCRIPT_MAX_CHARS
    (oldest lines dropped first, with an explicit omission marker so the model knows). Pure."""
    lines = [
        f"{_SPEAKER_LABELS.get(turn.speaker, turn.speaker.upper())}: {turn.content}"
        for turn in state.transcript
    ]
    text = "\n".join(lines)
    if not text:
        return "(no transcript)"
    dropped = False
    while len(text) > _TRANSCRIPT_MAX_CHARS and "\n" in text:
        text = text.split("\n", 1)[1]
        dropped = True
    if dropped:
        text = "(earlier turns omitted — the session record above is complete)\n" + text
    return text


def _build_assessment_messages(
    state: SessionState, excerpts: str = "", rules: str = "", *, expressive: bool = False
) -> list[dict[str, str]]:
    """Assemble the end-of-session assessment messages (persona + grounded record + transcript).
    Pure — retrieval happens in assess_session. `expressive` selects the audio-tag-authoring
    prompt variant (Track B) for the final ruling; default is byte-identical to before."""
    context = (
        f"{_grounded_context(state, excerpts, rules)}\n\n"
        # Same proceeding lens as the inline ruling: pending objections must be judged against the
        # right procedural frame, so the closing bench does not re-commit the argument/testimony
        # category error on any objection left pending.
        f"PROCEEDING TYPE: {state.proceeding_type or 'unspecified'}\n\n"
        f"FULL TRANSCRIPT:\n{_render_transcript(state)}"
    )
    instruction = "judge_assessment_expressive" if expressive else "judge_assessment"
    return [
        {"role": "system", "content": prompts.render("judge")},
        {"role": "system", "content": context},
        {"role": "user", "content": prompts.render(instruction)},
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
    # The live back-and-forth: the judge rules on a fragment IN CONTEXT of the exchange that led
    # to it (what OC argued, what the attorney was building toward), not on a sentence in a vacuum.
    recent = state.recent_exchange()
    exchange = f"RECENT EXCHANGE (oldest first):\n{recent}\n\n" if recent else ""
    user = (
        f"{_grounded_context(state, excerpts, rules)}\n\n"
        f"{exchange}"
        # The judge MUST know the proceeding to apply the right lens — "assumes facts" / "calls
        # for a legal conclusion" are proper objections at a witness examination but usually
        # improper against oral argument, where counsel argues the law and characterizes the
        # record (§13). Without this the judge ruled blind and reflexively sustained arguments.
        f"PROCEEDING TYPE: {state.proceeding_type or 'unspecified'}\n"
        f'ATTORNEY (statement objected to): "{fragment}"\n'
        f"OBJECTION: {objection.grounds} (raised by {objection.raised_by})"
    )
    return [
        {"role": "system", "content": prompts.render("judge_quick_ruling")},
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


@dataclass
class QuickRuling:
    """An inline ruling plus its §13 audit trail: which chunks the model was shown (turn-scoped)
    and which citations in its spoken reason were NOT grounded in them."""

    ruling: str
    reason: str
    chunk_ids: list[str] = field(default_factory=list)
    flagged_citations: list[str] = field(default_factory=list)


def quick_ruling(state: SessionState, objection: Objection, fragment: str) -> QuickRuling:
    """
    Inline ruling for a just-fired objection — the judge's real-time "Sustained/Overruled" (§6.5).
    Uses the FAST model (the objection classifier's config, gpt-oss class) because this sits
    directly in the live conversational path — same latency philosophy as the classifier and
    verification, NOT the reasoning model. Returns a QuickRuling (ruling + reason + provenance).
    Raises on any error or unparseable output — the caller stays silent and leaves the objection
    pending for the end-of-session assessment (never fabricate a ruling).
    """
    # Targeted §13 grounding: query = the objection's grounds + the objected statement. Fetched in
    # parallel with a TIGHT budget — this call already runs concurrently with the canned objection
    # line's playback (main.py), and a slow retrieval must not push the spoken ruling late; on
    # timeout the ruling simply proceeds ungrounded-but-recorded, same fail-open as everywhere.
    retrieval = court_knowledge.dual_retrieval(
        state.session_id,
        f"{objection.grounds}: {fragment}",
        timeout=court_knowledge.FAST_TIMEOUT,
    )
    excerpts, rules = retrieval.blocks()
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
    ruling, reason = _parse_quick_ruling(content)
    # §13 Phase 5: TURN-SCOPED citation check — compare against the chunks shown to THIS call,
    # never the corpus (a real-but-unretrieved citation still flags: asserted without being seen).
    # Flag + log, never rewrite the spoken output.
    flagged = citation_check.flag_ungrounded(reason, retrieval.shown_text)
    if flagged:
        logger.warning(
            "ungrounded citation(s) in inline ruling [session=%s path=objection_ruling "
            "citations=%s flagged=true]",
            state.session_id,
            flagged,
        )
    return QuickRuling(ruling, reason, retrieval.chunk_ids, flagged)


def assess_session(state: SessionState, *, expressive: bool = False) -> dict:
    """
    End-of-session pass: rule on every pending objection, extract established facts, and give a
    closing ruling — one live API call. Fails safe: on any error/unparseable output, returns no
    rulings (objections stay pending = not sustained, so the attorney is never penalized on a
    model failure), no facts, and a neutral closing ruling.

    `expressive` (Track B) authors ElevenLabs v3 audio-tag delivery cues into the closing ruling.
    Always returns BOTH `closing_ruling` (CLEAN — the source of truth for the transcript, scorecard,
    and citation check) and `closing_ruling_spoken` (the TTS input: tagged when expressive, else ==
    clean). When not expressive, the default path is byte-identical to before + the extra key.
    """
    # §13 grounding for the assessment: what is being judged is the pending objections (plus the
    # session's closing context), so the retrieval query is their grounds + the last attorney
    # turn — targeted, not a generic dump of the whole transcript.
    pending = ", ".join(o.grounds for o in state.pending_objections())
    last_turn = next(
        (t.content for t in reversed(state.transcript) if t.speaker == "attorney"), ""
    )
    # k=8 here (vs the default 4 elsewhere): the end-of-session ruling has confirmed latency slack
    # (spoken after the SessionFinale deliberation-wave), and with the §13 relevance floor a higher
    # k is a CAP not a floor — it can only surface MORE genuinely-relevant provisions, never pad.
    retrieval = court_knowledge.dual_retrieval(
        state.session_id, f"{pending} {last_turn}".strip(), k=8
    )
    excerpts, rules = retrieval.blocks()
    endpoint = build_endpoint(judge_config())
    try:
        content = chat(
            endpoint,
            _build_assessment_messages(state, excerpts, rules, expressive=expressive),
            temperature=0.3,
            # gpt-oss reasons before emitting; the assessment (rule every objection + extract facts
            # + closing ruling) needs a bigger budget than the classifier's 512, else the hidden
            # reasoning eats it all and content is empty (docs/LESSONS.md empty-content bug).
            max_tokens=1536,
            response_format={"type": "json_object"},
        )
        result = _parse_assessment(content)
    except Exception:
        return {
            "rulings": [],
            "established_facts": [],
            "closing_ruling": _FALLBACK_CLOSING,
            "closing_ruling_spoken": _FALLBACK_CLOSING,
            "chunk_ids": [],
            "flagged_citations": [],
        }
    if not result["closing_ruling"]:
        result["closing_ruling"] = _FALLBACK_CLOSING
    # Clean/tagged split (Track B): the CLEAN (stripped) ruling is the source of truth persisted,
    # displayed, and citation-checked; the tagged text is spoken by v3 only. When not expressive,
    # clean == raw (no strip), so this is a no-op beyond adding the key.
    raw_closing = result["closing_ruling"]
    clean_closing = audio_tags.strip_audio_tags(raw_closing) if expressive else raw_closing
    result["closing_ruling"] = clean_closing
    result["closing_ruling_spoken"] = raw_closing if expressive else clean_closing
    # §13 Phase 5: turn-scoped citation check on the CLEAN closing ruling (flag + log, no rewrite).
    flagged = citation_check.flag_ungrounded(clean_closing, retrieval.shown_text)
    if flagged:
        logger.warning(
            "ungrounded citation(s) in closing ruling [session=%s path=final_ruling "
            "citations=%s flagged=true]",
            state.session_id,
            flagged,
        )
    result["chunk_ids"] = retrieval.chunk_ids
    result["flagged_citations"] = flagged
    return result
