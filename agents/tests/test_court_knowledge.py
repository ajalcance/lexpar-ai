"""
File: agents/tests/test_court_knowledge.py
Purpose: Offline tests for the §13 dual-corpus grounding on the agents side — the court-rules
    retrieval module (block rendering, fail-open, parallel dual_blocks), the Judge's three
    grounded entry points (the audit-flagged missing-RAG fix), Opposing Counsel's rules block,
    and the classifier's tier-3 rules retrieval (fires only on the ambiguous path). All network
    is monkeypatched; state.session_id="" keeps every other suite retrieval-inert.
Depends on: pytest, court_knowledge, case_knowledge, judge, opposing_counsel,
    objection_classifier, session_state
Security notes: Fixture "rule" text is synthetic placeholder prose — never real statutory
    language (§13 no-fabrication constraint applies to tests too).
"""

import court_knowledge
import judge
import objection_classifier as oc
import opposing_counsel
from objection_classifier import ObjectionClassifier, classify_fragment
from session_state import SessionState

RULES_BLOCK = "RELEVANT PROCEDURAL RULES:\n- [Section 12] Placeholder rule text (not real)."
EXCERPTS_BLOCK = "RELEVANT PLEADING EXCERPTS:\n- Placeholder pleading passage."


# --- court_knowledge module ---------------------------------------------------------------------

def test_rules_block_renders_and_empty_guard():
    assert court_knowledge.rules_block([]) == ""
    block = court_knowledge.rules_block(["[Section 12] Placeholder.", "Other placeholder."])
    assert block.startswith("RELEVANT PROCEDURAL RULES:")
    assert "- [Section 12] Placeholder." in block


def test_retrieve_court_passages_short_circuits_and_fails_open(monkeypatch):
    # empty inputs: no network at all
    assert court_knowledge.retrieve_court_passages("", "q") == []
    assert court_knowledge.retrieve_court_passages("sess", "  ") == []
    # network failure: fail-open to []
    monkeypatch.setattr(
        court_knowledge.httpx, "get", lambda *a, **k: (_ for _ in ()).throw(OSError("down"))
    )
    assert court_knowledge.retrieve_court_passages("sess", "query") == []


def test_dual_retrieval_fetches_both_with_prefixed_provenance_ids(monkeypatch):
    monkeypatch.setattr(
        court_knowledge.case_knowledge,
        "retrieve_passage_refs",
        lambda sid, q, k=4, timeout=8.0: (["Placeholder pleading passage."], ["c1"]),
    )
    monkeypatch.setattr(
        court_knowledge,
        "retrieve_court_refs",
        lambda sid, q, k=4, timeout=8.0: (
            ["[Section 12] Placeholder rule text (not real)."],
            ["r1"],
        ),
    )
    retrieval = court_knowledge.dual_retrieval("sess", "query")
    assert retrieval.excerpts_block.startswith("RELEVANT PLEADING EXCERPTS:")
    assert retrieval.rules_block.startswith("RELEVANT PROCEDURAL RULES:")
    # provenance ids are table-prefixed so the audit row is self-describing
    assert retrieval.chunk_ids == ["case:c1", "court:r1"]
    # shown_text is EXACTLY the two blocks — the §13 citation check's comparison target
    assert "[Section 12]" in retrieval.shown_text
    # blocks-only convenience preserves the old shape
    assert court_knowledge.dual_blocks("sess", "query") == retrieval.blocks()


def test_dual_retrieval_short_circuits_without_session():
    assert court_knowledge.dual_blocks("", "query") == ("", "")
    assert court_knowledge.dual_blocks("sess", "   ") == ("", "")
    empty = court_knowledge.dual_retrieval("", "query")
    assert empty.chunk_ids == [] and empty.shown_text == ""


# --- SessionState plumbing fields ---------------------------------------------------------------

def test_session_state_plumbing_defaults_and_snapshot_unchanged():
    state = SessionState(case_facts="F")
    assert state.session_id == "" and state.court_id == "" and state.proceeding_type == ""
    grounded = SessionState(case_facts="F", session_id="s", court_id="c", proceeding_type="p")
    # plumbing fields are NOT record content — snapshot must not leak them
    assert "session_id" not in grounded.snapshot()
    assert grounded.snapshot() == state.snapshot()


# --- Judge grounding (the audit-flagged missing-RAG fix) ------------------------------------------

def test_judge_builders_include_both_blocks_when_present():
    state = SessionState(case_facts="F")
    joined = "\n".join(
        m["content"] for m in judge.build_messages(state, "turn", EXCERPTS_BLOCK, RULES_BLOCK)
    )
    assert "RELEVANT PLEADING EXCERPTS:" in joined
    assert "RELEVANT PROCEDURAL RULES:" in joined
    # and omitted (no stray headers) when absent
    plain = "\n".join(m["content"] for m in judge.build_messages(state, "turn"))
    assert "RELEVANT PROCEDURAL RULES:" not in plain

    objection = state.record_objection("relevance", "opposing_counsel")
    quick = "\n".join(
        m["content"]
        for m in judge._build_quick_ruling_messages(
            state, objection, "frag", EXCERPTS_BLOCK, RULES_BLOCK
        )
    )
    assert "RELEVANT PROCEDURAL RULES:" in quick

    assessment = "\n".join(
        m["content"] for m in judge._build_assessment_messages(state, EXCERPTS_BLOCK, RULES_BLOCK)
    )
    assert "RELEVANT PROCEDURAL RULES:" in assessment
    assert "FULL TRANSCRIPT:" in assessment


def _fake_retrieval() -> court_knowledge.Retrieval:
    return court_knowledge.Retrieval(
        excerpts_block=EXCERPTS_BLOCK,
        rules_block=RULES_BLOCK,
        chunk_ids=["case:c1", "court:r1"],
    )


def test_quick_ruling_retrieves_with_tight_timeout_and_grounds_prompt(monkeypatch):
    state = SessionState(case_facts="F", session_id="sess-1")
    objection = state.record_objection("relevance", "opposing_counsel")
    seen: dict = {}

    def fake_dual(session_id, query, *, k=4, timeout=8.0):
        seen.update(session_id=session_id, query=query, timeout=timeout)
        return _fake_retrieval()

    captured: dict = {}

    def fake_chat(endpoint, messages, **kwargs):
        captured["messages"] = messages
        # cites the SHOWN Section 12 (grounded) and an UNSHOWN Rule 99 (must flag, turn-scoped)
        return '{"ruling": "sustained", "reason": "Section 12 controls; see Rule 99"}'

    monkeypatch.setattr(judge.court_knowledge, "dual_retrieval", fake_dual)
    monkeypatch.setattr(judge, "chat", fake_chat)

    result = judge.quick_ruling(state, objection, "the fragment")
    assert result.ruling == "sustained"
    assert seen["session_id"] == "sess-1"
    assert "relevance" in seen["query"] and "the fragment" in seen["query"]
    assert seen["timeout"] == court_knowledge.FAST_TIMEOUT  # live-path budget, not the default
    joined = "\n".join(m["content"] for m in captured["messages"])
    assert "RELEVANT PROCEDURAL RULES:" in joined
    # §13 Phase 5: provenance carried through; only the unshown citation flags
    assert result.chunk_ids == ["case:c1", "court:r1"]
    assert result.flagged_citations == ["Rule 99"]


def test_assess_session_grounds_on_pending_objections(monkeypatch):
    state = SessionState(case_facts="F", session_id="sess-2")
    state.record_objection("relevance", "opposing_counsel")
    state.add_turn("attorney", "Closing statement placeholder.")
    seen: dict = {}

    def fake_dual(session_id, query, *, k=4, timeout=8.0):
        seen.update(session_id=session_id, query=query)
        return _fake_retrieval()

    captured: dict = {}

    def fake_chat(endpoint, messages, **kwargs):
        captured["messages"] = messages
        return (
            '{"rulings": ["overruled"], "established_facts": [], '
            '"closing_ruling": "Done, noting Rule 99."}'
        )

    monkeypatch.setattr(judge.court_knowledge, "dual_retrieval", fake_dual)
    monkeypatch.setattr(judge, "chat", fake_chat)

    result = judge.assess_session(state)
    assert result["closing_ruling"] == "Done, noting Rule 99."
    assert "relevance" in seen["query"]  # targeted on the pending objection
    assert "Closing statement placeholder." in seen["query"]
    joined = "\n".join(m["content"] for m in captured["messages"])
    assert "RELEVANT PROCEDURAL RULES:" in joined
    # §13 Phase 5: provenance + turn-scoped flag on the closing ruling (Rule 99 was not shown)
    assert result["chunk_ids"] == ["case:c1", "court:r1"]
    assert result["flagged_citations"] == ["Rule 99"]


def test_generate_ruling_grounds_when_session_id_present(monkeypatch):
    state = SessionState(case_facts="F", session_id="sess-3")
    monkeypatch.setattr(
        judge.court_knowledge, "dual_retrieval", lambda sid, q, **kw: _fake_retrieval()
    )
    captured: dict = {}

    def fake_chat(endpoint, messages, **kwargs):
        captured["messages"] = messages
        return '{"ruling": "Overruled."}'

    monkeypatch.setattr(judge, "chat", fake_chat)
    assert judge.generate_ruling(state, "turn") == "Overruled."
    joined = "\n".join(m["content"] for m in captured["messages"])
    assert "RELEVANT PROCEDURAL RULES:" in joined


# --- Opposing Counsel rules block -----------------------------------------------------------------

def test_oc_build_messages_keeps_blocks_separate():
    state = SessionState(case_facts="F")
    context = opposing_counsel.build_messages(state, "turn", EXCERPTS_BLOCK, RULES_BLOCK)[1][
        "content"
    ]
    assert "RELEVANT PLEADING EXCERPTS:" in context
    assert "RELEVANT PROCEDURAL RULES:" in context
    # two separate headed blocks, not one merged blob
    assert context.index("RELEVANT PLEADING EXCERPTS:") < context.index(
        "RELEVANT PROCEDURAL RULES:"
    )


# --- Classifier tier-3 rules retrieval -----------------------------------------------------------

def test_classifier_tier3_retrieves_rules_only_on_ambiguous_path(monkeypatch):
    calls: list[str] = []

    def fake_retrieve(session_id, query, k=4, timeout=8.0):
        calls.append(query)
        return ["[Section 12] Placeholder rule text (not real)."]

    captured: dict = {}

    def fake_chat(endpoint, messages, **kwargs):
        captured["messages"] = messages
        return '{"fire": false, "objection_type": null, "reason": "placeholder"}'

    monkeypatch.setattr(court_knowledge, "retrieve_court_passages", fake_retrieve)
    monkeypatch.setattr(oc, "chat", fake_chat)

    grounded = SessionState(case_facts="F", session_id="sess-4")
    # gate reject: no candidates → no retrieval, no LLM
    decision = classify_fragment("The contract was signed on March 3.", grounded)
    assert decision.outcome == oc.GATE_REJECTED
    assert calls == []
    # immediate fire (tier 2): no retrieval, no LLM
    decision = classify_fragment("Isn't it true you were there?", grounded)
    assert decision.outcome == oc.FIRE_IMMEDIATE
    assert calls == []
    # ambiguous candidate (tier 3): retrieval runs, rules block reaches the prompt
    decision = classify_fragment("I think he probably left early.", grounded)
    assert decision.outcome == oc.LLM_NO_FIRE
    assert len(calls) == 1
    assert "speculation" in calls[0]  # query carries the candidate ground(s)
    joined = "\n".join(m["content"] for m in captured["messages"])
    assert "RELEVANT PROCEDURAL RULES:" in joined


def test_classifier_offline_state_skips_retrieval(monkeypatch):
    # session_id="" (harnesses, other tests): retrieval must never be attempted
    def boom(*a, **k):
        raise AssertionError("retrieval attempted without a session id")

    monkeypatch.setattr(court_knowledge, "retrieve_court_passages", boom)
    monkeypatch.setattr(
        oc, "chat", lambda *a, **k: '{"fire": false, "objection_type": null, "reason": "r"}'
    )
    decision = classify_fragment("I think he probably left early.", SessionState())
    assert decision.outcome == oc.LLM_NO_FIRE  # LLM ran; retrieval was skipped, not failed


def test_classifier_wrapper_still_debounces_with_grounding(monkeypatch):
    monkeypatch.setattr(court_knowledge, "retrieve_court_passages", lambda *a, **k: [])
    monkeypatch.setattr(
        oc, "chat", lambda *a, **k: '{"fire": true, "objection_type": "speculation", "reason": "r"}'
    )
    classifier = ObjectionClassifier(SessionState(case_facts="F", session_id="sess-5"))
    first = classifier.consider("I think he probably left early.")
    assert first.fire
    grown = classifier.consider("I think he probably left early, before the meeting.")
    assert not grown.fire and grown.outcome == oc.DEBOUNCED


# --- §13 Phase 5: OC reply citation flagging (log-only path) --------------------------------------

def test_oc_stream_reply_logs_ungrounded_citation(monkeypatch, caplog):
    import logging

    import opposing_counsel as oc_mod

    monkeypatch.setattr(
        court_knowledge, "dual_retrieval", lambda sid, q, **kw: _fake_retrieval()
    )
    # the streamed reply cites shown Section 12 (fine) and unshown Rule 99 (flags)
    monkeypatch.setattr(
        oc_mod,
        "chat_stream",
        lambda *a, **k: iter(["Per Section 12, ", "and Rule 99, this fails."]),
    )
    with caplog.at_level(logging.WARNING, logger="lexpar.agents.oc"):
        spoken = "".join(oc_mod.stream_reply(SessionState(case_facts="F"), "turn", "sess-9"))
    assert "Rule 99" in spoken  # NEVER rewritten — flag, don't touch the spoken output
    flagged_lines = [r.message for r in caplog.records if "flagged=true" in r.message]
    assert len(flagged_lines) == 1
    assert "Rule 99" in flagged_lines[0] and "Section 12" not in flagged_lines[0]
    assert "path=oc_reply" in flagged_lines[0] and "sess-9" in flagged_lines[0]


def test_oc_stream_reply_no_flags_no_log(monkeypatch, caplog):
    import logging

    import opposing_counsel as oc_mod

    monkeypatch.setattr(
        court_knowledge, "dual_retrieval", lambda sid, q, **kw: _fake_retrieval()
    )
    monkeypatch.setattr(
        oc_mod, "chat_stream", lambda *a, **k: iter(["Grounded in Section 12 only."])
    )
    with caplog.at_level(logging.WARNING, logger="lexpar.agents.oc"):
        "".join(oc_mod.stream_reply(SessionState(case_facts="F"), "turn", "sess-9"))
    assert not [r for r in caplog.records if "flagged=true" in r.message]


# --- turn-scoped shown_text invariant (retrieval-accuracy changes must not break §13 grounding) --

def test_shown_text_is_exactly_the_retrieved_blocks_and_nothing_more():
    import case_knowledge
    from court_knowledge import Retrieval, rules_block

    # section-aware + exact-lookup passages flow through unchanged: shown_text (what citation_check
    # compares against) is EXACTLY the two blocks — every retrieved passage present, nothing else.
    passages = ["[Section 73] the squeeze-out provision text", "[Section 5] definitions text"]
    r = Retrieval(
        excerpts_block=case_knowledge.passages_block(["a pleading passage"]),
        rules_block=rules_block(passages),
        chunk_ids=["court:1", "court:2"],
    )
    assert r.shown_text == f"{r.excerpts_block}\n{r.rules_block}".strip()
    for passage in passages:
        assert passage in r.shown_text


def test_floor_zero_result_yields_no_rules_block_in_shown_text():
    import case_knowledge
    from court_knowledge import Retrieval, rules_block

    # D returning zero rule passages → empty rules block → shown_text carries only the excerpts
    # (the fail-open no-block path); citation_check then has no rule text to wrongly match against.
    r = Retrieval(
        excerpts_block=case_knowledge.passages_block(["a pleading passage"]),
        rules_block=rules_block([]),
        chunk_ids=[],
    )
    assert "RELEVANT PROCEDURAL RULES" not in r.shown_text
    assert r.shown_text == r.excerpts_block
