"""
File: agents/tests/test_verification_consistency.py
Purpose: Offline tests for the pure parts of the consistency check — message assembly and parsing
    of the verifier's JSON reply (including surrounding prose and malformed output). The live call
    itself is covered in test_live_fireworks.py. No network calls here.
Depends on: pytest, verification, session_state
"""

import pytest

from session_state import SessionState
from verification import _build_consistency_messages, _parse_consistency


def test_build_consistency_messages_include_record_and_reply():
    state = SessionState(case_facts="Contract dispute.")
    state.add_established_fact("Delivery was late.")
    messages = _build_consistency_messages("There was no contract.", state)
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "Contract dispute." in messages[1]["content"]
    assert "Delivery was late." in messages[1]["content"]
    assert "There was no contract." in messages[1]["content"]


def test_parse_consistency_extracts_contradictions():
    content = '{"consistent": false, "contradictions": ["draft denies the signed contract"]}'
    assert _parse_consistency(content) == ["draft denies the signed contract"]


def test_parse_consistency_tolerates_surrounding_prose():
    content = 'Here is the result:\n{"consistent": true, "contradictions": []}\nDone.'
    assert _parse_consistency(content) == []


def test_parse_consistency_raises_on_non_json():
    with pytest.raises(ValueError):
        _parse_consistency("no json object here")
