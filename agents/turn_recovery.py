"""
File: agents/turn_recovery.py
Purpose: Recover attorney turns the SDK silently drops. When a user turn completes while agent
    speech that does not allow interruptions is playing (OC's counter-argument, the canned objection
    line), livekit-agents logs "skipping reply to user input…" and RETURNS **before**
    on_user_turn_completed — so the turn never reaches the transcript, OC's context, or the record
    (verified against the installed SDK, agent_activity.py). This module is the safety net: every
    STT final is buffered here; when the next turn commits, buffered finals that the committed text
    does not cover are the DROPPED turn's words — flushed into the record with their original
    timestamps. Pure and offline-testable; the wiring lives in main.py (flag RECOVER_DROPPED_TURNS).
Depends on: stdlib only
Related: agents/main.py (wiring), docs/LESSONS.md (second casualty of OC non-interruptibility)
Security notes: Buffers spoken attorney content (work product) in memory for the session only;
    never logged (the recovery log line carries counts, not content).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def _norm(text: str) -> str:
    """Whitespace-collapsed, casefolded form for coverage comparison."""
    return " ".join(text.split()).casefold()


@dataclass
class PendingFinal:
    text: str
    spoken_at: datetime


@dataclass
class TurnRecovery:
    """Buffer of STT finals not yet covered by a committed turn."""

    _pending: list[PendingFinal] = field(default_factory=list)

    def note_final(self, text: str, spoken_at: datetime | None = None) -> None:
        """Record one STT final fragment (called for every is_final transcript event)."""
        cleaned = text.strip()
        if cleaned:
            self._pending.append(
                PendingFinal(cleaned, spoken_at or datetime.now(timezone.utc))
            )

    def reconcile(self, committed_text: str) -> list[PendingFinal]:
        """Called when a turn commits (on_user_turn_completed), BEFORE recording it. The committed
        text covers this turn's finals; anything buffered that it does NOT contain came from a turn
        the SDK dropped (skipped end-of-turn during non-interruptible speech) — returned, oldest
        first, for the caller to commit with the original timestamps. Clears the whole buffer either
        way. A fragment repeated verbatim in the committed turn is treated as covered — a rare,
        harmless collision (far better than today, where the entire dropped turn vanishes)."""
        committed = _norm(committed_text)
        leftovers = [
            pending
            for pending in self._pending
            if _norm(pending.text) and _norm(pending.text) not in committed
        ]
        self._pending.clear()
        return leftovers

    def drain(self) -> list[PendingFinal]:
        """Session end: whatever is still buffered belongs to a dropped turn that no committed
        turn followed — return it (oldest first) so the record is complete before assessment."""
        leftovers = list(self._pending)
        self._pending.clear()
        return leftovers
