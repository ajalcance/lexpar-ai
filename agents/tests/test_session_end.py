"""
File: agents/tests/test_session_end.py
Purpose: Offline tests for the agent's session-end assembly (Gap 4) — SessionState transcript
    accumulation and the deterministic scorecard heuristic (score, strengths cap, unique
    weaknesses, edge cases, verbatim ruling). No network. The persistence itself is covered by the
    backend TestClient test.
Depends on: pytest, session_state, scorecard_builder
"""

from scorecard_builder import build_session_end_payload
from session_state import SessionState


def _state_with_sustained(count: int) -> SessionState:
    state = SessionState(case_facts="Rivera v. Coastal Logistics.")
    for i in range(count):
        objection = state.record_objection("hearsay" if i % 2 else "leading", "opposing_counsel")
        state.rule_on_objection(objection, "sustained")
    return state


def test_add_turn_accumulates_transcript_in_order():
    state = SessionState()
    state.add_turn("attorney", "Good faith throughout.")
    state.add_turn("opposing_counsel", "Objection.", was_interruption=True)
    state.add_turn("judge", "Sustained.")
    assert [t.speaker for t in state.transcript] == ["attorney", "opposing_counsel", "judge"]
    assert state.transcript[1].was_interruption is True


def test_score_penalizes_sustained_objections():
    payload = build_session_end_payload(_state_with_sustained(2), "Holds up.")
    assert payload["overall_score"] == 84  # 100 - 8*2
    assert payload["judge_ruling"] == "Holds up."  # verbatim


def test_score_clamped_at_zero():
    payload = build_session_end_payload(_state_with_sustained(20), "r")
    assert payload["overall_score"] == 0  # never negative


def test_zero_sustained_objections_message():
    state = SessionState()
    state.add_established_fact("Contract signed on March 3.")
    payload = build_session_end_payload(state, "r")
    assert payload["overall_score"] == 100
    assert payload["weaknesses"] == "No objections were sustained against your argument."


def test_zero_established_facts_message():
    payload = build_session_end_payload(SessionState(), "r")
    assert payload["strengths"] == "No facts were formally established during this session."


def test_strengths_capped_at_five_most_recent():
    state = SessionState()
    for i in range(1, 8):  # 7 unique facts
        state.add_established_fact(f"Fact {i}.")
    payload = build_session_end_payload(state, "r")
    lines = payload["strengths"].splitlines()
    assert len(lines) == 5
    assert "Fact 7." in payload["strengths"]  # most recent kept
    assert "Fact 1." not in payload["strengths"]  # oldest dropped


def test_weaknesses_deduplicate_by_type():
    state = SessionState()
    for _ in range(3):
        objection = state.record_objection("hearsay", "opposing_counsel")
        state.rule_on_objection(objection, "sustained")
    payload = build_session_end_payload(state, "r")
    assert payload["weaknesses"].count("hearsay") == 1  # listed once, not thrice


def test_payload_transcript_shape():
    state = SessionState()
    state.add_turn("attorney", "Hello.")
    payload = build_session_end_payload(state, "r")
    turn = payload["transcript"][0]
    assert turn["speaker"] == "attorney"
    assert turn["content"] == "Hello."
    assert turn["was_interruption"] is False
    assert isinstance(turn["spoken_at"], str)  # ISO timestamp


# --- Report transcript: order by spoken time + merge fragments (coalesce_transcript) -------------

from datetime import datetime, timedelta, timezone  # noqa: E402

from scorecard_builder import coalesce_transcript  # noqa: E402


def _dt(offset_s: float) -> datetime:
    return datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc) + timedelta(seconds=offset_s)


def test_coalesce_orders_by_spoken_time_not_insertion():
    # The real ordering problem: an objection fires mid-utterance and is recorded FIRST (at +10),
    # while the attorney turn is committed later but timestamped at its START (+2). Ordering by
    # spoken_at puts the attorney's statement BEFORE the objection that responds to it.
    state = SessionState()
    state.add_turn(
        "opposing_counsel", "Objection — hearsay.", was_interruption=True, spoken_at=_dt(10)
    )
    state.add_turn("attorney", "My neighbor told me it was red.", spoken_at=_dt(2))
    state.add_turn("judge", "Sustained.", spoken_at=_dt(12))
    out = coalesce_transcript(state.transcript)
    assert [t.speaker for t in out] == ["attorney", "opposing_counsel", "judge"]


def test_coalesce_merges_same_speaker_fragments():
    state = SessionState()
    state.add_turn("attorney", "Your honor,", spoken_at=_dt(1))
    state.add_turn("attorney", "this case concerns the mortgage.", spoken_at=_dt(2))
    out = coalesce_transcript(state.transcript)
    assert len(out) == 1
    assert out[0].content == "Your honor, this case concerns the mortgage."
    assert out[0].spoken_at == _dt(1)  # keeps the earliest


def test_coalesce_keeps_objections_discrete():
    # Two barge-ins in a row are NOT merged — each objection stays its own line.
    state = SessionState()
    state.add_turn("opposing_counsel", "Objection — leading.", True, _dt(1))
    state.add_turn("opposing_counsel", "Objection — hearsay.", True, _dt(2))
    out = coalesce_transcript(state.transcript)
    assert len(out) == 2


def test_coalesce_does_not_mutate_state_transcript():
    state = SessionState()
    state.add_turn("attorney", "A", spoken_at=_dt(1))
    state.add_turn("attorney", "B", spoken_at=_dt(2))
    coalesce_transcript(state.transcript)
    assert [t.content for t in state.transcript] == ["A", "B"]  # raw capture untouched


def test_build_transcript_is_ordered_and_merged():
    state = SessionState()
    state.add_turn("opposing_counsel", "Objection.", was_interruption=True, spoken_at=_dt(5))
    state.add_turn("attorney", "Hello", spoken_at=_dt(1))
    state.add_turn("attorney", "world.", spoken_at=_dt(2))
    payload = build_session_end_payload(state, "ruling")
    rows = payload["transcript"]
    assert [r["speaker"] for r in rows] == ["attorney", "opposing_counsel"]
    assert rows[0]["content"] == "Hello world."


# --- performance rubric (scorecard depth): judge grade wins, heuristic is the fail-safe ---------


def test_judge_performance_score_overrides_heuristic():
    payload = build_session_end_payload(
        _state_with_sustained(2), "r", performance_score=71, performance_notes=[]
    )
    assert payload["overall_score"] == 71  # not 100 - 2*8


def test_missing_performance_score_falls_back_to_heuristic():
    payload = build_session_end_payload(_state_with_sustained(2), "r", performance_score=None)
    assert payload["overall_score"] == 84


def test_performance_notes_replace_hollow_no_objections_message():
    state = SessionState()
    payload = build_session_end_payload(
        state, "r", performance_score=78, performance_notes=["Repeated the ultra vires point"]
    )
    assert payload["weaknesses"] == "- Repeated the ultra vires point"
    assert "No objections were sustained" not in payload["weaknesses"]


def test_performance_notes_append_after_sustained_grounds():
    payload = build_session_end_payload(
        _state_with_sustained(1), "r", performance_notes=["Did not adjust after the ruling"]
    )
    assert "Sustained objection:" in payload["weaknesses"]
    assert payload["weaknesses"].endswith("- Did not adjust after the ruling")
