"""
File: agents/tests/test_session_state.py
Purpose: Tests for SessionState (ARCHITECTURE §6.5) — sample turns exercising the fact and
    objection ledgers and their update methods.
Depends on: pytest, session_state
"""

import pytest

from session_state import Objection, SessionState


def test_new_state_is_empty():
    state = SessionState(case_facts="Contract dispute.")
    assert state.case_facts == "Contract dispute."
    assert state.established_facts == []
    assert state.objections == []


def test_add_established_fact_appends_and_dedupes():
    state = SessionState()
    state.add_established_fact("Delivery was late.")
    state.add_established_fact("  Delivery was late.  ")  # duplicate after trimming
    state.add_established_fact("")  # blank ignored
    state.add_established_fact("Payment was withheld.")
    assert state.established_facts == ["Delivery was late.", "Payment was withheld."]


def test_record_objection_starts_pending():
    state = SessionState()
    objection = state.record_objection("hearsay", "opposing_counsel")
    assert objection.ruling == "pending"
    assert not objection.is_resolved
    assert state.pending_objections() == [objection]
    assert state.sustained_objections() == []


def test_rule_sustained_moves_to_sustained_ledger():
    state = SessionState()
    objection = state.record_objection("leading", "opposing_counsel")
    state.rule_on_objection(objection, "sustained")
    assert objection.ruling == "sustained"
    assert objection.is_resolved
    assert state.sustained_objections() == [objection]
    assert state.pending_objections() == []


def test_rule_overruled_is_not_sustained():
    state = SessionState()
    objection = state.record_objection("relevance", "attorney")
    state.rule_on_objection(objection, "overruled")
    assert objection.ruling == "overruled"
    assert state.sustained_objections() == []
    assert state.pending_objections() == []


def test_unknown_ruling_raises():
    state = SessionState()
    objection = state.record_objection("speculation", "opposing_counsel")
    with pytest.raises(ValueError):
        state.rule_on_objection(objection, "maybe")


def test_double_ruling_raises():
    state = SessionState()
    objection = state.record_objection("hearsay", "opposing_counsel")
    state.rule_on_objection(objection, "sustained")
    with pytest.raises(ValueError):
        state.rule_on_objection(objection, "overruled")


def test_inline_ruled_objection_is_not_re_ruled_at_session_end():
    # The "two code paths" the double-Sustained investigation flagged: an objection ruled INLINE
    # (quick_ruling) must not be ruled again by the end-of-session assessment. The ledger guards
    # this — a resolved objection drops out of pending_objections(), which is what assess_session
    # iterates, and a re-rule attempt raises. So it is ruled exactly once.
    state = SessionState()
    inline = state.record_objection("leading", "opposing_counsel")
    still_open = state.record_objection("speculation", "opposing_counsel")
    state.rule_on_objection(inline, "sustained")  # inline ruling during the session

    # assess_session only ever iterates the still-pending objections:
    assert state.pending_objections() == [still_open]
    assert inline not in state.pending_objections()
    # and the inline one can't be re-ruled (whichever path would try, it raises → callers catch):
    with pytest.raises(ValueError):
        state.rule_on_objection(inline, "overruled")
    assert inline.ruling == "sustained"  # unchanged


def test_ruling_on_foreign_objection_raises():
    state = SessionState()
    foreign = Objection(grounds="hearsay", raised_by="opposing_counsel")
    with pytest.raises(ValueError):
        state.rule_on_objection(foreign, "sustained")


def test_snapshot_contains_facts_and_objections():
    state = SessionState(case_facts="Wrongful termination.")
    state.add_established_fact("Plaintiff reported a safety violation.")
    objection = state.record_objection("hearsay", "opposing_counsel")
    state.rule_on_objection(objection, "sustained")

    snapshot = state.snapshot()
    assert "Wrongful termination." in snapshot
    assert "Plaintiff reported a safety violation." in snapshot
    assert "hearsay" in snapshot
    assert "sustained" in snapshot
