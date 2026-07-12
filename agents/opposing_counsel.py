"""
File: agents/opposing_counsel.py
Purpose: The Opposing Counsel agent. Loads its persona + sub-task prompts through the registry
    (prompts.render — opposing_counsel, oc_reply_style, oc_continuation*), assembles the session
    context (case facts + established facts + objection rulings) from
    SessionState, and generates the next spoken reply via the reasoning model (Fireworks today,
    self-hosted vLLM later — routed by llm_router). Two transports over the same messages:
    generate_reply (blocking, full completion) and stream_reply (yields text deltas for the
    sentence-level verification pipeline, §6.5). build_continuation_messages/stream_continuation
    are the mid-stream repair path: when a sentence fails verification, they prompt the model to
    continue from the already-spoken (verified) prefix without repeating the rejected claim.
    Message assembly is pure; only generate_reply/stream_reply/stream_continuation call the API.
Depends on: agents/prompts.py (prompt registry), agents/llm_router.py, agents/session_state.py
Related: agents/verification.py (verifies the draft), agents/streaming_verify.py (the per-sentence
    pipeline), agents/main.py (voice pipeline), docs/ARCHITECTURE.md §6 / §6.5
Security notes: Feeds case facts + live transcript (work product) to the model as prompt context —
    never log that context; it goes only to the configured endpoint.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

import prompts
from llm_router import build_endpoint, chat, chat_stream, opposing_counsel_config
from session_state import SessionState

logger = logging.getLogger("lexpar.agents.oc")

# OC replies are fast verbal sparring — one or two punchy sentences, not a brief. A tight token
# ceiling keeps them short (the "OC talks too long" complaint) AND cuts generation + TTS playout
# time; the oc_reply_style prompt is the primary brevity lever, this is the hard cap behind it.
_OC_REPLY_MAX_TOKENS = 140


def _context_block(state: SessionState) -> str:
    """The per-turn context: the durable record (snapshot) PLUS the live back-and-forth
    (recent_exchange) — without the latter OC is rebuilt amnesiac each turn: it cannot see its own
    prior replies (it repeated the same sentence across turns live), reference earlier statements,
    or build a cumulative line of attack. Shared by the reply and continuation builders."""
    context = f"SESSION RECORD (what is on the record so far):\n{state.snapshot()}"
    recent = state.recent_exchange()
    if recent:
        context += (
            "\n\nRECENT EXCHANGE (the live back-and-forth so far, oldest first — do not repeat "
            "points you have already made; advance your position):\n" + recent
        )
    return context


def build_messages(
    state: SessionState,
    attorney_turn: str,
    excerpts: str = "",
    rules: str = "",
    cutoff_note: str = "",
) -> list[dict[str, str]]:
    """Assemble the chat messages (persona + session record + optional retrieved pleading excerpts
    + optional retrieved procedural rules + the attorney's latest turn). `excerpts` (§12) and
    `rules` (§13) stay two clearly-separated blocks — case-specific fact vs generally-applicable
    rule must be distinguishable to the model. `cutoff_note` (floor dynamics) carries the memory of
    an interrupted reply into the retry — empty leaves the messages byte-identical to before."""
    context = _context_block(state)
    if excerpts:
        context += f"\n\n{excerpts}"
    if rules:
        context += f"\n\n{rules}"
    note = f"{cutoff_note}\n\n" if cutoff_note else ""
    user = (
        f'The attorney just argued:\n"{attorney_turn}"\n\n'
        f'{note}{prompts.render("oc_reply_style")}'
    )
    return [
        {"role": "system", "content": prompts.render("opposing_counsel")},
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
    context = _context_block(state)
    if spoken_prefix:
        situation = prompts.render(
            "oc_continuation", spoken_prefix=spoken_prefix, failure_reason=failure_reason
        )
    else:
        situation = prompts.render("oc_continuation_restart", failure_reason=failure_reason)
    user = (
        f'The attorney just argued:\n"{attorney_turn}"\n\n{situation}\n\n'
        f'{prompts.render("oc_reply_style")}'
    )
    return [
        {"role": "system", "content": prompts.render("opposing_counsel")},
        {"role": "system", "content": context},
        {"role": "user", "content": user},
    ]


def generate_reply(state: SessionState, attorney_turn: str) -> str:
    """Generate Opposing Counsel's next reply (blocking, full completion). Makes a live API call."""
    endpoint = build_endpoint(opposing_counsel_config())
    messages = build_messages(state, attorney_turn)
    return chat(endpoint, messages, temperature=0.7, max_tokens=_OC_REPLY_MAX_TOKENS).strip()


def stream_reply(
    state: SessionState, attorney_turn: str, session_id: str = "", cutoff_note: str = ""
) -> Iterator[str]:
    """Stream Opposing Counsel's next reply as text deltas. Makes a live API call. If `session_id`
    is given, retrieves BOTH the pleading passages (§12) and the forum's procedural-rule passages
    (§13) relevant to this turn — fetched in parallel — and grounds the reply in them
    (best-effort — retrieval failure just proceeds on the case summary). After the stream
    completes, the full reply gets the §13 TURN-SCOPED citation check against exactly what this
    turn's prompt carried — flags are LOGGED (labels only), never rewritten out of the reply;
    ruling provenance rows are the Judge's paths, per the §13 design."""
    excerpts, rules = "", ""
    retrieval = None
    if session_id:
        import court_knowledge

        retrieval = court_knowledge.dual_retrieval(session_id, attorney_turn)
        excerpts, rules = retrieval.blocks()
    endpoint = build_endpoint(opposing_counsel_config())
    spoken: list[str] = []
    for delta in chat_stream(
        endpoint,
        build_messages(state, attorney_turn, excerpts, rules, cutoff_note),
        temperature=0.7,
        max_tokens=_OC_REPLY_MAX_TOKENS,
    ):
        spoken.append(delta)
        yield delta
    if retrieval is not None:
        import citation_check

        flagged = citation_check.flag_ungrounded("".join(spoken), retrieval.shown_text)
        if flagged:
            logger.warning(
                "ungrounded citation(s) in OC reply [session=%s path=oc_reply citations=%s "
                "flagged=true]",
                session_id,
                flagged,
            )


def stream_continuation(
    state: SessionState, attorney_turn: str, spoken_prefix: str, failure_reason: str
) -> Iterator[str]:
    """Stream the repair continuation after a mid-stream verification failure. Live API call."""
    endpoint = build_endpoint(opposing_counsel_config())
    messages = build_continuation_messages(state, attorney_turn, spoken_prefix, failure_reason)
    yield from chat_stream(endpoint, messages, temperature=0.7, max_tokens=_OC_REPLY_MAX_TOKENS)
