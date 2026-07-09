"""
File: agents/tests/test_live_fireworks.py
Purpose: LIVE tests that make real Fireworks API calls — generation (opposing counsel, judge), the
    consistency verifier, and the objection classifier. Marked `live` and DESELECTED from CI by
    pyproject's `addopts = -m 'not live'`; run explicitly with `pytest -m live` (needs
    FIREWORKS_API_KEY).
Depends on: pytest, opposing_counsel, judge, verification, objection_classifier, session_state
"""

import pytest

import judge
import opposing_counsel
from objection_classifier import classify_fragment
from session_state import SessionState
from verification import check_consistency

pytestmark = pytest.mark.live


def _demo_state() -> SessionState:
    state = SessionState(case_facts="Rivera v. Coastal Logistics: wrongful-termination claim.")
    state.add_established_fact("The employment contract was signed on March 3.")
    return state


def test_generate_reply_returns_text():
    reply = opposing_counsel.generate_reply(_demo_state(), "My client acted in good faith.")
    assert isinstance(reply, str)
    assert reply.strip()


def test_generate_ruling_returns_text():
    ruling = judge.generate_ruling(_demo_state(), "Objection, Your Honor — hearsay.")
    assert isinstance(ruling, str)
    assert ruling.strip()


def test_assess_session_rules_and_returns_well_formed_shape():
    # Two pending objections + a transcript → the judge returns exactly one ruling per objection
    # (sustained/overruled), a facts list, and a non-empty closing ruling.
    state = _demo_state()
    state.add_turn("attorney", "My client told me his supervisor said the report wouldn't matter.")
    state.record_objection("hearsay", "opposing_counsel")
    state.add_turn("attorney", "The contract was signed on March 3, isn't that right?")
    state.record_objection("leading", "opposing_counsel")

    result = judge.assess_session(state)
    assert len(result["rulings"]) == 2
    assert all(r in ("sustained", "overruled") for r in result["rulings"])
    assert isinstance(result["established_facts"], list)
    assert result["closing_ruling"].strip()


def test_consistency_flags_a_contradiction():
    # The reply denies an established fact; the verifier should flag at least one contradiction.
    contradictions = check_consistency(
        "There was never any signed employment contract in this case.", _demo_state()
    )
    assert isinstance(contradictions, list)
    assert len(contradictions) >= 1


def test_consistency_passes_a_faithful_reply():
    contradictions = check_consistency(
        "As the record reflects, the employment contract was signed on March 3.", _demo_state()
    )
    assert contradictions == []


def test_objection_fires_on_leading_question():
    decision = classify_fragment(
        "Isn't it true that you never actually read the contract before signing it?", _demo_state()
    )
    assert decision.fire is True


def test_objection_fires_on_hearsay():
    decision = classify_fragment(
        "My neighbor told me he saw the defendant run the red light.", _demo_state()
    )
    assert decision.fire is True


def test_objection_holds_on_clean_statement():
    decision = classify_fragment("The contract was signed on March 3.", _demo_state())
    assert decision.fire is False
