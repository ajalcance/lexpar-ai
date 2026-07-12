"""
File: agents/tests/test_floor_dynamics.py
Purpose: Unit tests for the floor-contest state machine (floor_dynamics.FloorTracker) — the
    corroboration/veto/promotion logic, the one-retry cap, the judge-order streak + cooldown, and
    the objection-supersedes rule. All with a fake clock; no livekit.
Depends on: pytest, floor_dynamics
"""

import floor_dynamics
from floor_dynamics import (
    JUDGE_ORDER_COOLDOWN_S,
    JUDGE_ORDER_STREAK,
    PROMOTION_WINDOW_S,
    FloorTracker,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def make() -> tuple[FloorTracker, FakeClock]:
    clock = FakeClock()
    return FloorTracker(clock=clock), clock


def test_cut_off_promoted_by_committed_turn_yields_one_retry():
    tracker, _ = make()
    tracker.reply_cut_off("Your honor, the record", "the mortgage is void")
    tracker.attorney_turn_committed()
    assert tracker.take_retry() == ("Your honor, the record", "the mortgage is void")
    assert tracker.take_retry() is None  # one retry per point — consumed


def test_candidate_without_committed_turn_never_becomes_retry():
    tracker, _ = make()
    tracker.reply_cut_off("partial", "turn")
    assert tracker.take_retry() is None  # no corroborating attorney turn


def test_candidate_expires_beyond_promotion_window():
    tracker, clock = make()
    tracker.reply_cut_off("partial", "turn")
    clock.now += PROMOTION_WINDOW_S + 1
    tracker.attorney_turn_committed()
    assert tracker.take_retry() is None


def test_false_interruption_vetoes_candidate():
    tracker, _ = make()
    tracker.reply_cut_off("partial", "turn")
    tracker.false_interruption()
    tracker.attorney_turn_committed()
    assert tracker.take_retry() is None


def test_objection_supersedes_pending_retry():
    tracker, _ = make()
    tracker.reply_cut_off("partial", "turn")
    tracker.attorney_turn_committed()
    tracker.objection_fired()
    assert tracker.take_retry() is None


def test_completed_reply_resets_the_contest():
    tracker, _ = make()
    tracker.reply_cut_off("partial", "turn")
    tracker.attorney_turn_committed()
    tracker.reply_completed()
    assert tracker.take_retry() is None
    assert tracker.should_judge_intervene() is False  # streak reset too


def _corroborated_cut_off(tracker: FloorTracker, n: int) -> None:
    for i in range(n):
        tracker.reply_cut_off(f"partial {i}", f"turn {i}")
        tracker.attorney_turn_committed()


def test_judge_intervenes_at_streak_threshold_and_consumes_it():
    tracker, _ = make()
    _corroborated_cut_off(tracker, JUDGE_ORDER_STREAK - 1)
    assert tracker.should_judge_intervene() is False
    _corroborated_cut_off(tracker, 1)
    assert tracker.should_judge_intervene() is True
    assert tracker.should_judge_intervene() is False  # streak consumed by the intervention


def test_judge_order_cooldown_blocks_until_elapsed():
    tracker, clock = make()
    _corroborated_cut_off(tracker, JUDGE_ORDER_STREAK)
    assert tracker.should_judge_intervene() is True
    _corroborated_cut_off(tracker, JUDGE_ORDER_STREAK)
    assert tracker.should_judge_intervene() is False  # inside cooldown
    clock.now += JUDGE_ORDER_COOLDOWN_S + 1
    assert tracker.should_judge_intervene() is True  # streak persisted, cooldown elapsed


def test_cutoff_note_carries_the_partial_when_present():
    note = floor_dynamics.cutoff_note("the lease is not in evidence", "the deal was fraudulent")
    assert "the lease is not in evidence" in note
    assert "finish that point" in note


def test_cutoff_note_falls_back_to_the_original_turn_when_nothing_was_voiced():
    note = floor_dynamics.cutoff_note("", "the deal was fraudulent")
    assert "the deal was fraudulent" in note
