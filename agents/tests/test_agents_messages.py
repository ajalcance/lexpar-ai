"""
File: agents/tests/test_agents_messages.py
Purpose: Offline tests for the pure message-assembly of the agents — persona prompt loads, and
    build_messages includes the session record and the attorney's turn. No network calls.
Depends on: pytest, opposing_counsel, judge, session_state
"""

import pytest

import judge
import opposing_counsel
from session_state import SessionState


def _state() -> SessionState:
    state = SessionState(case_facts="Rivera v. Coastal Logistics.")
    state.add_established_fact("Plaintiff reported a safety violation.")
    return state


def test_opposing_counsel_prompt_loads():
    assert "opposing counsel" in opposing_counsel.load_prompt().lower()


def test_judge_prompt_loads():
    assert "judge" in judge.load_prompt().lower()


def test_opposing_counsel_messages_include_record_and_turn():
    messages = opposing_counsel.build_messages(_state(), "My client acted in good faith.")
    assert messages[0]["role"] == "system"
    assert messages[-1]["role"] == "user"
    joined = "\n".join(m["content"] for m in messages)
    assert "Rivera v. Coastal Logistics." in joined
    assert "Plaintiff reported a safety violation." in joined
    assert "My client acted in good faith." in joined


def test_judge_messages_include_record_and_turn():
    messages = judge.build_messages(_state(), "Objection, hearsay.")
    joined = "\n".join(m["content"] for m in messages)
    assert "Rivera v. Coastal Logistics." in joined
    assert "Objection, hearsay." in joined


def test_judge_parse_ruling_extracts_text():
    assert judge._parse_ruling('{"ruling": "Sustained. Move on."}') == "Sustained. Move on."


def test_judge_parse_ruling_tolerates_prose_and_raises_on_junk():
    assert judge._parse_ruling('ok: {"ruling": "Overruled."} done') == "Overruled."
    with pytest.raises(ValueError):
        judge._parse_ruling("no json here")
