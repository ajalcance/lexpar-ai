"""
File: agents/judge_voice.py
Purpose: LiveKit-free selection logic for how the Judge speaks (ARCHITECTURE §6.5): prefer the
    real judge participant (judge_participant.py — attribution by construction), and on ANY
    failure fall back to the previous working path (session.say on the shared agent participant +
    the synthetic judge_speaking label events). This is the safety guarantee for the participant
    migration: if LiveKit refuses anything at runtime, a session degrades to exactly the old
    behavior — never to a silent judge.
Depends on: logging (stdlib only — no livekit import, so it is CI-unit-testable)
Related: agents/judge_participant.py (primary), agents/main.py (builds both callables),
    docs/ARCHITECTURE.md §6.5, tasks/PLAN.md (design doc)
Security notes: Handles ruling text only; logs outcomes, never the text.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("lexpar.agents.judge")


class JudgeVoice:
    """
    Speak as the Judge through `primary` (the real judge participant), falling back to `fallback`
    (the session-multiplexed voice) when the primary is unavailable or fails mid-call. Both are
    injected async callables `(text) -> None`, so this policy is unit-tested without livekit.
    """

    def __init__(self, primary=None, fallback=None) -> None:
        if fallback is None:
            raise ValueError("JudgeVoice requires a fallback speaker")
        self._primary = primary
        self._fallback = fallback

    async def say(
        self, text: str, *, expressive: bool = False, expressive_text: str | None = None
    ) -> bool:
        """Speak `text`; returns True if the primary (judge participant) carried it, False if the
        fallback did. A fallback failure propagates — callers already guard judge speech.

        Track B: for the final ruling the caller passes `expressive=True` + `expressive_text` (the
        v3 audio-tag version). The PRIMARY (v3 judge participant) speaks the tagged text; the
        FALLBACK always speaks the clean `text` — so a degraded fallback on flash never voices
        literal '[sighs]'. Inline rulings call with the defaults (clean text, flash)."""
        spoken = expressive_text if (expressive and expressive_text is not None) else text
        if self._primary is not None:
            try:
                await self._primary(spoken, expressive=expressive)
                return True
            except Exception:
                logger.exception(
                    "judge participant failed to speak — falling back to session voice"
                )
        await self._fallback(text)
        return False
