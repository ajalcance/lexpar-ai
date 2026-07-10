"""
File: agents/tests/test_judge_assessment.py
Purpose: Offline tests for the judge's end-of-session assessment (ARCHITECTURE §6.5) — the pure
    message assembly (`_build_assessment_messages`, incl. the rendered transcript) and JSON parsing
    (`_parse_assessment`: rulings normalized to sustained/overruled, established facts, closing
    ruling), plus `assess_session`'s fail-safe on unparseable/empty output (model call monkeypatched
    — no network). Live behavior is in test_live_fireworks.py.
Depends on: pytest, judge, session_state
"""

from __future__ import annotations

import pytest

import judge as judge_mod
from session_state import SessionState


def _seeded_state() -> SessionState:
    state = SessionState(case_facts="Rivera v. Coastal Logistics.")
    state.add_turn("attorney", "My client was terminated in retaliation.")
    state.record_objection("hearsay", "opposing_counsel")
    state.record_objection("leading", "opposing_counsel")
    return state


# --- _build_assessment_messages (pure) -------------------------------------------------------

def test_build_assessment_messages_includes_record_and_transcript():
    state = _seeded_state()
    messages = judge_mod._build_assessment_messages(state)
    assert messages[0]["role"] == "system"  # persona
    context = messages[1]["content"]
    assert "SESSION RECORD:" in context
    assert "FULL TRANSCRIPT:" in context
    assert "ATTORNEY: My client was terminated in retaliation." in context  # rendered transcript
    assert "hearsay" in context  # objection ledger present for the judge to rule on


def test_render_transcript_labels_speakers():
    state = SessionState()
    state.add_turn("attorney", "Point one.")
    state.add_turn("opposing_counsel", "Objection — leading.", was_interruption=True)
    rendered = judge_mod._render_transcript(state)
    assert "ATTORNEY: Point one." in rendered
    assert "OPPOSING COUNSEL: Objection — leading." in rendered


def test_render_transcript_empty():
    assert judge_mod._render_transcript(SessionState()) == "(no transcript)"


# --- _parse_assessment (pure) ----------------------------------------------------------------

def test_parse_assessment_normalizes_rulings():
    content = (
        '{"rulings": ["Sustained", "overruled", "banana"], '
        '"established_facts": ["Contract signed March 3", "  ", "Report filed May 2"], '
        '"closing_ruling": "So ordered."}'
    )
    result = judge_mod._parse_assessment(content)
    assert result["rulings"] == ["sustained", "overruled", "overruled"]  # unknown → overruled
    # blank entries dropped:
    assert result["established_facts"] == ["Contract signed March 3", "Report filed May 2"]
    assert result["closing_ruling"] == "So ordered."


def test_parse_assessment_tolerates_missing_fields():
    result = judge_mod._parse_assessment('{"closing_ruling": "Continue."}')
    assert result["rulings"] == []
    assert result["established_facts"] == []
    assert result["closing_ruling"] == "Continue."


def test_parse_assessment_raises_on_non_json():
    with pytest.raises(ValueError):
        judge_mod._parse_assessment("no json here")


# --- assess_session fail-safe (model call monkeypatched) -------------------------------------

def test_assess_session_parses_live_shape(monkeypatch):
    monkeypatch.setattr(
        judge_mod,
        "chat",
        lambda *a, **k: '{"rulings": ["sustained", "overruled"], '
        '"established_facts": ["A fact"], "closing_ruling": "Sustained in part."}',
    )
    result = judge_mod.assess_session(_seeded_state())
    assert result["rulings"] == ["sustained", "overruled"]
    assert result["established_facts"] == ["A fact"]
    assert result["closing_ruling"] == "Sustained in part."


def test_assess_session_fails_safe_on_garbage(monkeypatch):
    # Unparseable output → no rulings (objections stay pending = not sustained, no penalty), no
    # facts, and a neutral closing ruling. Never crashes the shutdown path.
    monkeypatch.setattr(judge_mod, "chat", lambda *a, **k: "the model rambled with no json")
    result = judge_mod.assess_session(_seeded_state())
    assert result["rulings"] == []
    assert result["established_facts"] == []
    assert result["closing_ruling"] == judge_mod._FALLBACK_CLOSING


def test_assess_session_fills_empty_closing_ruling(monkeypatch):
    monkeypatch.setattr(
        judge_mod, "chat", lambda *a, **k: '{"rulings": [], "closing_ruling": ""}'
    )
    result = judge_mod.assess_session(_seeded_state())
    assert result["closing_ruling"] == judge_mod._FALLBACK_CLOSING


def test_assess_session_fails_safe_on_error(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("verifier down")

    monkeypatch.setattr(judge_mod, "chat", boom)
    result = judge_mod.assess_session(_seeded_state())
    assert result["rulings"] == []
    assert result["closing_ruling"] == judge_mod._FALLBACK_CLOSING


# --- quick_ruling (inline judge ruling, model call monkeypatched) -----------------------------

def _pending_objection(state: SessionState):
    return state.pending_objections()[0]


def test_quick_ruling_messages_include_objection_and_fragment():
    state = _seeded_state()
    messages = judge_mod._build_quick_ruling_messages(
        state, _pending_objection(state), "He told me it was red."
    )
    user = messages[-1]["content"]
    assert "hearsay" in user
    assert "He told me it was red." in user
    assert "SESSION RECORD:" in user


def test_parse_quick_ruling_valid():
    ruling, reason = judge_mod._parse_quick_ruling(
        '{"ruling": "Sustained", "reason": "classic hearsay"}'
    )
    assert ruling == "sustained"
    assert reason == "classic hearsay"


def test_parse_quick_ruling_rejects_unknown_ruling():
    with pytest.raises(ValueError):
        judge_mod._parse_quick_ruling('{"ruling": "maybe", "reason": "unsure"}')


def test_parse_quick_ruling_rejects_non_json():
    with pytest.raises(ValueError):
        judge_mod._parse_quick_ruling("the model rambled")


def test_quick_ruling_returns_parsed_pair(monkeypatch):
    monkeypatch.setattr(
        judge_mod, "chat", lambda *a, **k: '{"ruling": "overruled", "reason": "goes to weight"}'
    )
    state = _seeded_state()
    ruling, reason = judge_mod.quick_ruling(state, _pending_objection(state), "fragment")
    assert (ruling, reason) == ("overruled", "goes to weight")


def test_quick_ruling_raises_so_caller_fails_safe(monkeypatch):
    # quick_ruling propagates errors; the caller (main.judge_rule) stays silent and leaves the
    # objection PENDING for the end-of-session assessment — never a fabricated spoken ruling.
    def boom(*a, **k):
        raise RuntimeError("timeout")

    monkeypatch.setattr(judge_mod, "chat", boom)
    state = _seeded_state()
    with pytest.raises(RuntimeError):
        judge_mod.quick_ruling(state, _pending_objection(state), "fragment")
    assert _pending_objection(state).ruling == "pending"  # ledger untouched on failure
