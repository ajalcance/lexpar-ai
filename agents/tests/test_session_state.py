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


def test_snapshot_includes_case_summary_when_present():
    from session_state import SessionState

    state = SessionState(case_facts="thin facts", case_summary="PARTIES: A v. B. CLAIM: breach.")
    snap = state.snapshot()
    assert "CASE SUMMARY (from the pleading):" in snap
    assert "PARTIES: A v. B. CLAIM: breach." in snap
    # absent when there is no pleading summary
    assert "CASE SUMMARY" not in SessionState(case_facts="x").snapshot()


def test_snapshot_includes_matter_when_present():
    from session_state import SessionState

    state = SessionState(case_facts="x", matter="The court decides defendant's motion to dismiss.")
    snap = state.snapshot()
    assert "MATTER BEFORE THE COURT:" in snap
    assert "The court decides defendant's motion to dismiss." in snap
    # absent (and the shared frame is simply omitted) when no matter was derived
    assert "MATTER BEFORE THE COURT" not in SessionState(case_facts="x").snapshot()


def test_snapshot_includes_case_profile_when_present():
    from session_state import SessionState

    state = SessionState(
        case_facts="x",
        case_number="G.R. No. 218738",
        petitioner="Metropolitan Bank & Trust Company",
        respondent="Salazar Realty Corporation",
        represented_party="respondent",
        relief_sought="Nullification of the mortgage and foreclosure; quieting of title.",
    )
    snap = state.snapshot()
    assert "CASE PROFILE (stated by counsel at case creation — authoritative):" in snap
    assert "- Case number: G.R. No. 218738" in snap
    assert "- Petitioner: Metropolitan Bank & Trust Company" in snap
    # The side line fixes BOTH sides by declaration.
    assert (
        "The attorney arguing this session represents the respondent "
        "(Salazar Realty Corporation); opposing counsel represents the petitioner "
        "(Metropolitan Bank & Trust Company)." in snap
    )
    assert "- Relief sought by the attorney: Nullification of the mortgage" in snap
    # No profile → no block (pre-profile cases unchanged).
    assert "CASE PROFILE" not in SessionState(case_facts="x").snapshot()


def test_fresh_sessions_are_independent_no_ledger_bleed():
    # Session isolation: two rehearsals of the SAME case share the case facts but wholly separate
    # ledgers. Guards against a mutable-default-arg regression (all the ledgers use default_factory)
    # that would silently share state across every session in the worker.
    from session_state import SessionState

    first = SessionState(case_facts="Same case.")
    second = SessionState(case_facts="Same case.")
    first.add_established_fact("Fact only in session one.")
    objection = first.record_objection("hearsay", "opposing_counsel")
    first.rule_on_objection(objection, "sustained")
    first.add_turn("attorney", "Argument only in session one.")

    # The second session is untouched — no fact, objection, or transcript crossed over.
    assert second.established_facts == []
    assert second.objections == []
    assert second.transcript == []
    assert "Fact only in session one." not in second.snapshot()
    assert "Argument only in session one." not in second.recent_exchange()


# --- recent_exchange (the conversation memory carried into per-turn prompts) -------------------


def test_recent_exchange_labels_and_orders_turns_oldest_first():
    state = SessionState()
    state.add_turn("attorney", "The mortgage is void.")
    state.add_turn("opposing_counsel", "The record does not support that.")
    state.add_turn("judge", "Overruled.")
    exchange = state.recent_exchange()
    assert exchange == (
        "ATTORNEY: The mortgage is void.\n"
        "OPPOSING COUNSEL: The record does not support that.\n"
        "JUDGE: Overruled."
    )


def test_recent_exchange_keeps_only_the_last_max_turns():
    state = SessionState()
    for i in range(15):
        state.add_turn("attorney", f"turn {i}")
    exchange = state.recent_exchange(max_turns=10)
    assert "turn 4" not in exchange
    assert exchange.startswith("ATTORNEY: turn 5")
    assert exchange.endswith("ATTORNEY: turn 14")


def test_recent_exchange_drops_oldest_lines_to_fit_char_cap():
    state = SessionState()
    state.add_turn("attorney", "a" * 900)
    state.add_turn("opposing_counsel", "b" * 900)
    state.add_turn("judge", "c" * 900)
    exchange = state.recent_exchange(max_chars=2000)
    assert "a" * 900 not in exchange  # oldest dropped
    assert "b" * 900 in exchange and "c" * 900 in exchange


def test_recent_exchange_empty_transcript_is_empty_string():
    assert SessionState().recent_exchange() == ""
