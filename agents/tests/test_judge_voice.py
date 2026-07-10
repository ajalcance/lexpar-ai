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
    """Records say() calls; optionally raises to simulate a failing path."""

    def __init__(self, raises: bool = False):
        self.spoken: list[str] = []
        self.raises = raises

    async def __call__(self, text: str) -> None:
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
