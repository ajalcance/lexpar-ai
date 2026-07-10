"""
File: agents/tests/test_judge_voice.py
Purpose: Offline tests for the judge voice selection policy (agents/judge_voice.py) — the
    livekit-free wrapper that prefers the real judge participant and falls back to the
    session-multiplexed voice on ANY failure, so a LiveKit refusal degrades to the previous
    working behavior instead of a silent judge (the safety requirement of the judge-participant
    migration; ARCHITECTURE §6.5).
Depends on: pytest, judge_voice
"""

from __future__ import annotations

import asyncio

import pytest

from judge_voice import JudgeVoice


class Speaker:
    """Records say() calls; optionally raises to simulate a failing path. Accepts the `expressive`
    kwarg the primary is called with (the fallback is called without it)."""

    def __init__(self, raises: bool = False):
        self.spoken: list[str] = []
        self.raises = raises

    async def __call__(self, text: str, *, expressive: bool = False) -> None:
        if self.raises:
            raise RuntimeError("speaker down")
        self.spoken.append(text)


def test_primary_carries_the_line_when_healthy():
    primary, fallback = Speaker(), Speaker()
    used_primary = asyncio.run(JudgeVoice(primary, fallback).say("Sustained."))
    assert used_primary is True
    assert primary.spoken == ["Sustained."]
    assert fallback.spoken == []  # fallback untouched on the happy path


def test_falls_back_when_primary_fails():
    primary, fallback = Speaker(raises=True), Speaker()
    used_primary = asyncio.run(JudgeVoice(primary, fallback).say("Overruled."))
    assert used_primary is False
    assert fallback.spoken == ["Overruled."]  # the judge is never silenced by a participant failure


def test_goes_straight_to_fallback_without_a_primary():
    fallback = Speaker()
    used_primary = asyncio.run(JudgeVoice(None, fallback).say("Sustained."))
    assert used_primary is False
    assert fallback.spoken == ["Sustained."]


def test_fallback_failure_propagates_to_the_caller():
    # Callers (judge_rule/_finalize_session) already guard judge speech — the wrapper must not
    # swallow a total failure silently.
    primary, fallback = Speaker(raises=True), Speaker(raises=True)
    with pytest.raises(RuntimeError):
        asyncio.run(JudgeVoice(primary, fallback).say("Sustained."))


def test_requires_a_fallback():
    with pytest.raises(ValueError):
        JudgeVoice(Speaker(), None)


def test_expressive_primary_speaks_the_tagged_text():
    # Track B: the v3 primary gets the tagged (audio-tag) text.
    primary, fallback = Speaker(), Speaker()
    asyncio.run(
        JudgeVoice(primary, fallback).say(
            "So ordered.", expressive=True, expressive_text="[solemnly] So ordered."
        )
    )
    assert primary.spoken == ["[solemnly] So ordered."]
    assert fallback.spoken == []


def test_expressive_fallback_never_gets_the_tagged_text():
    # If the v3 primary fails, the fallback (flash) must speak the CLEAN text — never literal tags.
    primary, fallback = Speaker(raises=True), Speaker()
    asyncio.run(
        JudgeVoice(primary, fallback).say(
            "So ordered.", expressive=True, expressive_text="[solemnly] So ordered."
        )
    )
    assert fallback.spoken == ["So ordered."]  # clean, no tags


def test_inline_ruling_defaults_carry_clean_text_to_primary():
    # Inline rulings call with defaults (no expressive) — primary gets the plain text.
    primary, fallback = Speaker(), Speaker()
    asyncio.run(JudgeVoice(primary, fallback).say("Sustained."))
    assert primary.spoken == ["Sustained."]
