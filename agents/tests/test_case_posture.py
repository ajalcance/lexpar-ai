"""
File: agents/tests/test_case_posture.py
Purpose: Offline tests for the session-start "matter before the court" derivation (case_posture) —
    pure message assembly (build_matter_messages), JSON parsing (parse_matter, fail-safe), and
    derive_matter's guards (empty inputs → no call; unparseable/error → "" so the session degrades
    to no explicit matter). The model call is monkeypatched — no network.
Depends on: pytest, case_posture, session_state
"""

from __future__ import annotations

import case_posture
from session_state import SessionState


def test_build_matter_messages_includes_case_materials_and_proceeding():
    state = SessionState(
        case_facts="Rivera seeks reinstatement.",
        case_summary="Wrongful-termination complaint; Rivera v. Coastal.",
        proceeding_type="oral_argument",
    )
    messages = case_posture.build_matter_messages(state)
    assert messages[0]["role"] == "system"  # the derive_matter framing instruction
    user = messages[1]["content"]
    assert "oral_argument" in user
    assert "Rivera v. Coastal" in user
    assert "Rivera seeks reinstatement." in user


def test_build_matter_messages_tolerates_missing_materials():
    user = case_posture.build_matter_messages(SessionState())[1]["content"]
    assert "(no pleading summary)" in user
    assert "(none provided)" in user
    assert "unspecified" in user  # proceeding type default


def test_parse_matter_extracts_and_trims():
    assert (
        case_posture.parse_matter('{"matter": "  The court decides X.  "}')
        == "The court decides X."
    )
    # Tolerates surrounding prose around the JSON object.
    assert case_posture.parse_matter('Sure: {"matter": "Y"} done') == "Y"


def test_parse_matter_fails_safe():
    assert case_posture.parse_matter("not json at all") == ""
    assert case_posture.parse_matter('{"other": "z"}') == ""  # missing field
    assert case_posture.parse_matter('{"matter": "   "}') == ""  # blank
    assert case_posture.parse_matter("{bad json") == ""


def test_derive_matter_skips_call_when_no_materials(monkeypatch):
    called = {"n": 0}

    def _boom(*a, **k):
        called["n"] += 1
        raise AssertionError("should not call the model with no materials")

    monkeypatch.setattr(case_posture, "chat", _boom)
    assert case_posture.derive_matter(SessionState()) == ""
    assert called["n"] == 0


def test_derive_matter_parses_model_output(monkeypatch):
    monkeypatch.setattr(case_posture, "chat", lambda *a, **k: '{"matter": "Motion to dismiss."}')
    state = SessionState(case_facts="Some facts.")
    assert case_posture.derive_matter(state) == "Motion to dismiss."


def test_derive_matter_fails_safe_on_error(monkeypatch):
    def _raise(*a, **k):
        raise RuntimeError("endpoint down")

    monkeypatch.setattr(case_posture, "chat", _raise)
    assert case_posture.derive_matter(SessionState(case_summary="X")) == ""
