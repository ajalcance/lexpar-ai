"""
File: agents/tests/test_turn_recovery.py
Purpose: Offline tests for the dropped-turn safety net (turn_recovery.py) — finals buffered, the
    committed turn's own finals cleared (covered), a DROPPED turn's finals returned with their
    original timestamps, and the session-end drain. This guards the record against the SDK
    discarding a user turn that completes during non-interruptible agent speech (docs/LESSONS.md).
Depends on: pytest, turn_recovery
"""

from __future__ import annotations

from datetime import datetime, timezone

from turn_recovery import TurnRecovery


def _ts(second: int) -> datetime:
    return datetime(2026, 7, 12, 8, 0, second, tzinfo=timezone.utc)


def test_committed_turn_covers_its_own_finals():
    recovery = TurnRecovery()
    recovery.note_final("Your honor,", _ts(1))
    recovery.note_final("the mortgage is void.", _ts(2))
    # The SDK commits the joined turn — both finals are covered, nothing to recover.
    assert recovery.reconcile("Your honor, the mortgage is void.") == []
    # Buffer cleared: the next reconcile starts fresh.
    assert recovery.reconcile("anything") == []


def test_dropped_turn_finals_are_recovered_with_timestamps():
    recovery = TurnRecovery()
    # Turn A (spoken while OC's non-interruptible reply played) — the SDK dropped it: no commit.
    recovery.note_final("Metro Bank knew full well the board lacked authority.", _ts(1))
    # Turn B commits normally.
    recovery.note_final("On that basis the foreclosure is void.", _ts(5))
    leftovers = recovery.reconcile("On that basis the foreclosure is void.")
    assert [pending.text for pending in leftovers] == [
        "Metro Bank knew full well the board lacked authority."
    ]
    assert leftovers[0].spoken_at == _ts(1)  # original stretch timestamp, not recovery time


def test_coverage_is_whitespace_and_case_insensitive():
    recovery = TurnRecovery()
    recovery.note_final("THE  BOARD   resolution", _ts(1))
    assert recovery.reconcile("the board resolution approves it") == []


def test_blank_finals_ignored():
    recovery = TurnRecovery()
    recovery.note_final("   ", _ts(1))
    recovery.note_final("", None)
    assert recovery.reconcile("anything") == []
    assert recovery.drain() == []


def test_drain_returns_uncommitted_finals_for_session_end():
    recovery = TurnRecovery()
    recovery.note_final("Final statement before ending.", _ts(9))
    drained = recovery.drain()
    assert [pending.text for pending in drained] == ["Final statement before ending."]
    assert drained[0].spoken_at == _ts(9)
    assert recovery.drain() == []  # cleared


def test_note_final_defaults_timestamp_when_stretch_start_unknown():
    recovery = TurnRecovery()
    recovery.note_final("No start signal captured.", None)
    drained = recovery.drain()
    assert drained[0].spoken_at is not None  # stamped at arrival, never None
