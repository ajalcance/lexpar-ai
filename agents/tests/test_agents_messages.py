"""
File: agents/tests/test_agents_messages.py
Purpose: Offline tests for the pure message-assembly of the agents — persona prompt loads, and
    build_messages includes the session record and the attorney's turn. No network calls.
Depends on: pytest, opposing_counsel, judge, session_state
"""

import pytest

import judge
import opposing_counsel
import prompts
from session_state import SessionState


def _state() -> SessionState:
    state = SessionState(case_facts="Rivera v. Coastal Logistics.")
    state.add_established_fact("Plaintiff reported a safety violation.")
    return state


def test_opposing_counsel_prompt_loads():
    assert "opposing counsel" in prompts.render("opposing_counsel").lower()


def test_judge_prompt_loads():
    assert "judge" in prompts.render("judge").lower()


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


def test_opposing_counsel_build_messages_includes_pleading_excerpts():
    import opposing_counsel
    from session_state import SessionState

    state = SessionState(case_facts="F")
    excerpts = "RELEVANT PLEADING EXCERPTS:\n- The report was filed March 3."
    context = opposing_counsel.build_messages(state, "the attorney turn", excerpts)[1]["content"]
    assert "RELEVANT PLEADING EXCERPTS:" in context
    assert "The report was filed March 3." in context
    # and omitted when there are none
    plain = opposing_counsel.build_messages(state, "turn")[1]["content"]
    assert "RELEVANT PLEADING EXCERPTS:" not in plain


def test_case_knowledge_passages_block_and_empty_guard():
    import case_knowledge

    assert case_knowledge.passages_block([]) == ""
    block = case_knowledge.passages_block(["Fact one.", "Fact two."])
    assert block.startswith("RELEVANT PLEADING EXCERPTS:")
    assert "- Fact one." in block and "- Fact two." in block
    # retrieval short-circuits (no network) for empty inputs
    assert case_knowledge.retrieve_passages("", "q") == []
    assert case_knowledge.retrieve_passages("sess", "   ") == []


def test_opposing_counsel_messages_include_recent_exchange_when_present():
    state = _state()
    state.add_turn("attorney", "The mortgage is void ab initio.")
    state.add_turn("opposing_counsel", "The record does not support that characterization.")
    context = opposing_counsel.build_messages(state, "next turn")[1]["content"]
    assert "RECENT EXCHANGE" in context
    assert "OPPOSING COUNSEL: The record does not support that characterization." in context
    # empty transcript → no block (offline harnesses unchanged)
    assert "RECENT EXCHANGE" not in opposing_counsel.build_messages(_state(), "t")[1]["content"]


def test_quick_ruling_messages_include_recent_exchange_and_proceeding():
    from session_state import SessionState

    state = SessionState(proceeding_type="oral_argument")
    state.add_turn("attorney", "Demand on the board would have been futile.")
    objection = state.record_objection(grounds="assumes_facts", raised_by="opposing_counsel")
    user = judge._build_quick_ruling_messages(state, objection, "the fragment")[1]["content"]
    assert "RECENT EXCHANGE" in user
    assert "ATTORNEY: Demand on the board would have been futile." in user
    assert "PROCEEDING TYPE: oral_argument" in user


def test_is_pass_recognizes_only_the_bare_sentinel():
    from opposing_counsel import is_pass

    # The sentinel, tolerant of punctuation/quotes/case the model may add.
    assert is_pass("PASS")
    assert is_pass("Pass.")
    assert is_pass('"PASS"')
    assert is_pass("  pass  ")
    # Real sentences are never swallowed — full-sentence match only.
    assert not is_pass("Passing over that point, the record is clear.")
    assert not is_pass("The court should not give this a pass.")
    assert not is_pass("")
