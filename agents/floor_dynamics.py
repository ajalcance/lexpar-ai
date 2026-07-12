"""
File: agents/floor_dynamics.py
Purpose: Natural floor-contest dynamics (flag-gated: config.FLOOR_DYNAMICS). When the attorney
    talks over Opposing Counsel's reply, a real advocate doesn't silently abandon the point — they
    ask for the floor ("Your honor, may I be heard?") and, if the attorney keeps interrupting, the
    bench intervenes ("Counsel, you will allow opposing counsel to be heard."). FloorTracker is the
    LiveKit-free state machine behind that: it records a cut-off as a CANDIDATE only, promotes it to
    a retry only when the interrupting speech becomes a real committed attorney turn (an echo/VAD
    blip never does), lets the SDK's false-interruption signal veto it, caps OC at one retry per
    point, and gates the judge's order behind a streak threshold + cooldown so the bench intervenes
    sparingly. A structured objection supersedes the courtesy dance entirely (object → rule →
    continue). Because OC's prompt is rebuilt fresh each turn (no chat history), the tracker also
    carries the MEMORY a retry needs: the partial reply already voiced and the attorney statement it
    was answering, so the completed point is continuous, not amnesiac.
Depends on: time (stdlib only — unit-testable without livekit)
Related: agents/main.py (wires it into llm_node / on_user_turn_completed / judge_rule /
    agent_false_interruption), agents/opposing_counsel.py (cutoff_note), docs/ARCHITECTURE.md §6.5
Security notes: Holds a fragment of OC's own reply and the attorney's turn in memory only — work
    product; never logged, only fed back into the reply prompt.
"""

from __future__ import annotations

import time

# Canned lines — deterministic, instant, no factual claims (so they skip verification, same
# rationale as the canned objection line).
OC_FLOOR_REQUEST = "Your honor, may I be heard?"
JUDGE_ORDER_LINE = "Counsel, you will allow opposing counsel to be heard."

# A cut-off candidate is promoted only if the interrupting speech becomes a committed attorney
# turn within this window — otherwise it expires as noise.
PROMOTION_WINDOW_S = 10.0
# Consecutive corroborated cut-offs before the bench intervenes, and how long it stays quiet after.
JUDGE_ORDER_STREAK = 2
JUDGE_ORDER_COOLDOWN_S = 180.0


class FloorTracker:
    """Per-session floor-contest state. All methods are cheap and synchronous; the injectable
    clock keeps the window/cooldown logic unit-testable."""

    def __init__(self, clock=time.monotonic) -> None:
        self._clock = clock
        # (partial_reply, attorney_turn, at) — a cut-off awaiting corroboration.
        self._candidate: tuple[str, str, float] | None = None
        # (partial_reply, attorney_turn) — a corroborated cut-off entitling ONE retry.
        self._pending: tuple[str, str] | None = None
        self._streak = 0
        self._last_order_at: float | None = None

    def reply_cut_off(self, partial: str, attorney_turn: str) -> None:
        """OC's reply generator was closed before completing (candidate only — an echo that
        pauses OC also lands here, so promotion waits for a real attorney turn)."""
        self._candidate = (partial, attorney_turn, self._clock())

    def reply_completed(self) -> None:
        """A reply finished uninterrupted — the contest is over; everything resets."""
        self._candidate = None
        self._pending = None
        self._streak = 0

    def false_interruption(self) -> None:
        """The SDK concluded the interruption was noise — veto the candidate."""
        self._candidate = None

    def objection_fired(self) -> None:
        """A structured objection supersedes the courtesy dance: object → rule → continue,
        never 'may I be heard' after a ruling."""
        self._candidate = None
        self._pending = None

    def attorney_turn_committed(self) -> None:
        """The interrupting speech became a real transcribed turn — promote the candidate."""
        if self._candidate is None:
            return
        partial, turn, at = self._candidate
        self._candidate = None
        if self._clock() - at > PROMOTION_WINDOW_S:
            return
        self._pending = (partial, turn)
        self._streak += 1

    def take_retry(self) -> tuple[str, str] | None:
        """Consume the retry entitlement (one per point). Returns (partial, attorney_turn)."""
        pending, self._pending = self._pending, None
        return pending

    def should_judge_intervene(self) -> bool:
        """True when the streak hits the threshold and the cooldown has passed. Consuming: an
        intervention resets the streak and starts the cooldown."""
        if self._streak < JUDGE_ORDER_STREAK:
            return False
        now = self._clock()
        if (
            self._last_order_at is not None
            and now - self._last_order_at < JUDGE_ORDER_COOLDOWN_S
        ):
            return False
        self._last_order_at = now
        self._streak = 0
        return True


def cutoff_note(partial: str, attorney_turn: str) -> str:
    """The memory a retry carries into the reply prompt — OC's prompt is rebuilt fresh each turn,
    so without this the retry would ask for the floor and then argue something unrelated."""
    if partial:
        return (
            f'You were interrupted mid-reply after saying: "{partial}" — finish that point in '
            "one short sentence, then address the attorney's latest statement."
        )
    return (
        "You were interrupted before you could respond to the attorney's previous statement: "
        f'"{attorney_turn}" — briefly make that point now as part of your reply.'
    )
