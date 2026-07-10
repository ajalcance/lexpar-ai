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


def test_is_valid_session_id_accepts_uuids_rejects_room_artifacts():
    # The worker no-ops in rooms that aren't real sessions ("session-<uuid>"): scratch/test rooms
    # (e.g. the judge-participant verification room) otherwise 422 on every backend call.
    import backend_client

    assert backend_client.is_valid_session_id("699efd2d-2427-4c76-a8c5-26da01033d2f") is True
    assert backend_client.is_valid_session_id("judge-verify") is False
    assert backend_client.is_valid_session_id("") is False
