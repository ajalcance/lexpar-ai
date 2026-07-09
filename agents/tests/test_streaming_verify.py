"""
File: agents/tests/test_streaming_verify.py
Purpose: Offline tests for the streaming sentence-level verification pipeline (ARCHITECTURE §6.5)
    — incremental sentence segmentation (with the legal-abbreviation guard), per-sentence
    verification with accumulated context, the Option B failure mode (one repair continuation,
    then truncation), fail-closed behavior on verifier/stream errors, the async bridge, and the
    streaming plumbing in opposing_counsel / llm_router (no network — everything injected or
    stubbed).
Depends on: pytest, streaming_verify, opposing_counsel, llm_router, session_state
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import opposing_counsel
from llm_router import LlmEndpoint, chat_stream
from session_state import SessionState
from streaming_verify import SentenceSegmenter, astream_verified_reply, stream_verified_reply

# --- SentenceSegmenter -------------------------------------------------------------------------


def segment(text: str, chunk: int = 1) -> list[str]:
    """Feed text through the segmenter in `chunk`-sized deltas (default 1 char — worst case)."""
    segmenter = SentenceSegmenter()
    out: list[str] = []
    for i in range(0, len(text), chunk):
        out.extend(segmenter.feed(text[i : i + chunk]))
    tail = segmenter.flush()
    if tail:
        out.append(tail)
    return out


def test_segmenter_splits_basic_sentences():
    assert segment("The first point stands. The second point falls. ") == [
        "The first point stands.",
        "The second point falls.",
    ]


def test_segmenter_keeps_case_citation_intact():
    text = "Brown v. Board of Education, 347 U.S. 483 (1954), controls here. Next point."
    assert segment(text, chunk=3) == [
        "Brown v. Board of Education, 347 U.S. 483 (1954), controls here.",
        "Next point.",
    ]


def test_segmenter_guards_titles_and_abbreviations():
    assert segment("Mr. Rivera testified under oath. No. 5 is dispositive.") == [
        "Mr. Rivera testified under oath.",
        "No. 5 is dispositive.",
    ]


def test_segmenter_splits_question_and_exclamation():
    assert segment("Was he there? He was not! The record shows it.") == [
        "Was he there?",
        "He was not!",
        "The record shows it.",
    ]


def test_segmenter_does_not_split_before_lowercase():
    # A period followed by a lowercase token reads as an abbreviation, not a sentence end.
    assert segment("She paused. then continued without a break.") == [
        "She paused. then continued without a break."
    ]


def test_segmenter_flush_returns_trailing_fragment():
    segmenter = SentenceSegmenter()
    assert segmenter.feed("An unfinished thought") == []
    assert segmenter.flush() == "An unfinished thought"
    assert segmenter.flush() is None


def test_segmenter_keeps_closing_quote_with_sentence():
    assert segment('He said "done." The court agreed.') == [
        'He said "done."',
        "The court agreed.",
    ]


# --- stream_verified_reply: helpers -------------------------------------------------------------


def _gen(*chunks: str):
    """A fake generation stream factory yielding the given deltas."""

    def factory(state: SessionState, turn: str):
        yield from chunks

    return factory


def _repair(*chunks: str):
    """A fake repair stream factory that records its (prefix, reason) calls."""
    calls: list[tuple[str, str]] = []

    def factory(state: SessionState, turn: str, prefix: str, reason: str):
        calls.append((prefix, reason))
        yield from chunks

    factory.calls = calls  # type: ignore[attr-defined]
    return factory


def _clean(draft: str, state: SessionState) -> list[str]:
    return []


# --- stream_verified_reply: clean path -----------------------------------------------------------


def test_stream_yields_verified_sentences_in_order():
    out = list(
        stream_verified_reply(
            SessionState(),
            "turn",
            generate=_gen("First point. ", "Second point."),
            repair=_repair(),
            consistency=_clean,
        )
    )
    assert out == ["First point.", "Second point."]


def test_consistency_called_per_sentence_with_accumulated_context():
    drafts: list[str] = []

    def consistency(draft: str, state: SessionState) -> list[str]:
        drafts.append(draft)
        return []

    list(
        stream_verified_reply(
            SessionState(),
            "turn",
            generate=_gen("One stands. ", "Two follows."),
            repair=_repair(),
            consistency=consistency,
        )
    )
    # Each sentence is verified with the already-verified prefix as context.
    assert drafts == ["One stands.", "One stands. Two follows."]


# --- stream_verified_reply: Option B failure mode ------------------------------------------------


def _flag_march15(draft: str, state: SessionState) -> list[str]:
    if "March 15" in draft:
        return ["the record says the contract was signed March 3, not March 15"]
    return []


def test_failing_sentence_triggers_one_repair_and_drops_the_rest():
    repair = _repair("A safe continuation follows.")
    out = list(
        stream_verified_reply(
            SessionState(),
            "turn",
            generate=_gen(
                "The report is dated May 2. ",
                "It was signed March 15. ",
                "Never spoken aloud.",
            ),
            repair=repair,
            consistency=_flag_march15,
        )
    )
    # Failed sentence + the rest of its stream discarded; the verified repair is spoken instead.
    assert out == ["The report is dated May 2.", "A safe continuation follows."]
    assert len(repair.calls) == 1
    prefix, reason = repair.calls[0]
    assert prefix == "The report is dated May 2."
    assert reason.startswith("contradicts the session record:")


def test_repair_failure_falls_back_to_truncation():
    repair = _repair("Still March 15 nonsense.")  # the repair itself fails verification
    out = list(
        stream_verified_reply(
            SessionState(),
            "turn",
            generate=_gen("The report is dated May 2. ", "It was signed March 15."),
            repair=repair,
            consistency=_flag_march15,
        )
    )
    assert out == ["The report is dated May 2."]  # Option A fallback: truncate
    assert len(repair.calls) == 1  # exactly one repair attempt, never a second


def test_first_sentence_failure_repairs_with_empty_prefix():
    repair = _repair("A clean opening statement.")
    out = list(
        stream_verified_reply(
            SessionState(),
            "turn",
            generate=_gen("It was signed March 15. ", "More argument."),
            repair=repair,
            consistency=_flag_march15,
        )
    )
    assert out == ["A clean opening statement."]
    assert repair.calls[0][0] == ""  # nothing spoken yet — repair regenerates from scratch


def test_suspicious_citation_treated_as_failure():
    # Citation-heuristic hit takes the SAME failure path as a contradiction (no special-casing).
    repair = _repair("No citation this time.")
    out = list(
        stream_verified_reply(
            SessionState(),
            "turn",
            generate=_gen("See 123 Xyz.4th 456 (2050) for support. ", "More argument."),
            repair=repair,
            consistency=_clean,
        )
    )
    assert out == ["No citation this time."]
    assert repair.calls[0][1].startswith("suspicious citation:")


# --- stream_verified_reply: fail-closed on errors ------------------------------------------------


def test_verifier_exception_stops_stream_fail_closed():
    def consistency(draft: str, state: SessionState) -> list[str]:
        if "Two" in draft:
            raise RuntimeError("verifier down")
        return []

    out = list(
        stream_verified_reply(
            SessionState(),
            "turn",
            generate=_gen("One stands. ", "Two follows. ", "Three closes."),
            repair=_repair("never used"),
            consistency=consistency,
        )
    )
    # Verifier infrastructure error: nothing further can be verified, so no repair — truncate.
    assert out == ["One stands."]


def test_generation_error_stops_at_last_verified_sentence():
    def factory(state: SessionState, turn: str):
        yield "One stands! "
        yield "T"
        raise RuntimeError("stream dropped")

    out = list(
        stream_verified_reply(
            SessionState(), "turn", generate=factory, repair=_repair(), consistency=_clean
        )
    )
    assert out == ["One stands!"]


# --- async bridge --------------------------------------------------------------------------------


def test_async_bridge_yields_the_same_sentences():
    async def collect() -> list[str]:
        return [
            s
            async for s in astream_verified_reply(
                SessionState(),
                "turn",
                generate=_gen("First point. ", "Second point."),
                repair=_repair(),
                consistency=_clean,
            )
        ]

    assert asyncio.run(collect()) == ["First point.", "Second point."]


# --- opposing_counsel streaming plumbing (no network) --------------------------------------------


def test_stream_reply_reuses_build_messages(monkeypatch):
    captured: dict = {}

    def fake_stream(endpoint, messages, **kwargs):
        captured["messages"] = messages
        yield "Reply."

    monkeypatch.setattr(opposing_counsel, "chat_stream", fake_stream)
    state = SessionState(case_facts="Rivera v. Coastal Logistics.")
    out = list(opposing_counsel.stream_reply(state, "the attorney turn"))
    assert out == ["Reply."]
    assert captured["messages"] == opposing_counsel.build_messages(state, "the attorney turn")


def test_continuation_messages_include_prefix_and_reason():
    messages = opposing_counsel.build_continuation_messages(
        SessionState(), "turn", "Already said this aloud.", "contradicts the record: X"
    )
    user = messages[-1]["content"]
    assert "Already said this aloud." in user
    assert "contradicts the record: X" in user


def test_continuation_messages_without_prefix():
    messages = opposing_counsel.build_continuation_messages(
        SessionState(), "turn", "", "suspicious citation: 1 Fake 2 (2050)"
    )
    user = messages[-1]["content"]
    assert "suspicious citation: 1 Fake 2 (2050)" in user
    assert "already said" not in user.lower()  # no phantom prefix in the empty-prefix variant


# --- llm_router.chat_stream (stubbed client) -----------------------------------------------------


def test_chat_stream_yields_deltas_and_requests_streaming():
    calls: dict = {}

    def create(**kwargs):
        calls.update(kwargs)
        return [
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="Hel"))]),
            SimpleNamespace(choices=[]),  # keep-alive chunk with no choices
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="lo."))]),
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=None))]),
        ]

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    endpoint = LlmEndpoint(client=client, model="test-model")  # type: ignore[arg-type]
    out = list(chat_stream(endpoint, [{"role": "user", "content": "hi"}]))
    assert out == ["Hel", "lo."]
    assert calls["stream"] is True
    assert calls["model"] == "test-model"
