"""
File: agents/tests/test_objection_classifier.py
Purpose: Offline tests for the objection classifier (ARCHITECTURE §6) — the recall-biased gate
    (tier 1) on a labeled sample set, the precision-biased high-confidence gate (tier 2) and its
    immediate-fire-without-LLM path, the fail-closed / short-circuit / parse behavior of
    classify_fragment's LLM stage (tier 3, model call monkeypatched — no network), the six-outcome
    audit trail, and the per-utterance debounce. Live model behavior is covered in
    test_live_fireworks.py.
Depends on: pytest, objection_classifier, session_state
"""

import pytest

import objection_classifier as oc
from objection_classifier import (
    Decision,
    ObjectionClassifier,
    candidate_grounds,
    classify_fragment,
    high_confidence_grounds,
)
from session_state import SessionState

# An ambiguous gate candidate — flagged by the recall gate but NOT high-confidence, so it is the
# one that actually exercises the tier-3 LLM path.
AMBIGUOUS = "I think he probably left early."

# --- Tier 1: recall-biased gate on a labeled sample set --------------------------------------

def test_gate_flags_leading_question():
    assert "leading" in candidate_grounds("Isn't it true that you were there that night?")


def test_gate_flags_tag_question():
    assert "leading" in candidate_grounds("You signed it on the 3rd, didn't you?")


def test_gate_flags_hearsay():
    assert "hearsay" in candidate_grounds("He told me the light was red.")


def test_gate_flags_speculation():
    assert "speculation" in candidate_grounds(AMBIGUOUS)


def test_gate_ignores_clean_statement():
    assert candidate_grounds("The contract was signed on March 3.") == []


# --- Tier 2: precision-biased high-confidence gate -------------------------------------------

def test_high_confidence_flags_clear_leading():
    assert high_confidence_grounds("Isn't it true you were there that night?") == ["leading"]
    assert "leading" in high_confidence_grounds("You signed it on the 3rd, didn't you?")


def test_high_confidence_flags_direct_hearsay():
    assert high_confidence_grounds("He told me the light was red.") == ["hearsay"]


def test_high_confidence_excludes_bare_question():
    # A bare trailing "?" is a recall-gate candidate (leading) but NOT high-confidence — it must
    # still go to the LLM, not fire immediately.
    frag = "Where were you that night?"
    assert "leading" in candidate_grounds(frag)
    assert high_confidence_grounds(frag) == []


def test_high_confidence_excludes_speculation():
    assert candidate_grounds(AMBIGUOUS) == ["speculation"]
    assert high_confidence_grounds(AMBIGUOUS) == []


def test_high_confidence_ignores_clean_statement():
    assert high_confidence_grounds("The contract was signed on March 3.") == []


# --- Tier 2: immediate fire (no LLM call) ----------------------------------------------------

def test_high_confidence_fires_immediately_without_llm(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("LLM must not be called for a high-confidence fragment")

    monkeypatch.setattr(oc, "chat", boom)
    decision = classify_fragment("Isn't it true you lied?", SessionState())
    assert decision.fire is True
    assert decision.objection_type == "leading"
    assert decision.outcome == oc.FIRE_IMMEDIATE


def test_high_confidence_hearsay_fires_immediately(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("LLM must not be called for a high-confidence fragment")

    monkeypatch.setattr(oc, "chat", boom)
    decision = classify_fragment("He told me the defendant ran the light.", SessionState())
    assert decision.fire is True
    assert decision.objection_type == "hearsay"
    assert decision.outcome == oc.FIRE_IMMEDIATE


def test_immediate_type_priority_prefers_leading():
    # Matches BOTH high-confidence hearsay ("told me") and leading ("wouldn't you agree") — leading
    # wins per the cross-exam priority.
    decision = classify_fragment(
        "He told me the light was red, wouldn't you agree?", SessionState()
    )
    assert decision.outcome == oc.FIRE_IMMEDIATE
    assert decision.objection_type == "leading"


# --- Tier 3: classify_fragment LLM plumbing (model call monkeypatched — no network) ----------

def test_clean_fragment_short_circuits_without_llm(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("LLM must not be called for a clean fragment")

    monkeypatch.setattr(oc, "chat", boom)
    decision = classify_fragment("The invoice is dated April 2.", SessionState())
    assert decision.fire is False
    assert decision.outcome == oc.GATE_REJECTED


def test_ambiguous_candidate_reaches_llm(monkeypatch):
    calls: list[str] = []

    def record(*args, **kwargs):
        calls.append("called")
        return '{"fire": false, "objection_type": null, "reason": "no"}'

    monkeypatch.setattr(oc, "chat", record)
    classify_fragment(AMBIGUOUS, SessionState())
    assert calls == ["called"]  # the ambiguous candidate went to the LLM, not immediate-fired


def test_ambiguous_candidate_parses_fire(monkeypatch):
    monkeypatch.setattr(
        oc,
        "chat",
        lambda *a, **k: '{"fire": true, "objection_type": "Speculation", "reason": "guessing"}',
    )
    decision = classify_fragment(AMBIGUOUS, SessionState())
    assert decision.fire is True
    assert decision.objection_type == "speculation"
    assert decision.outcome == oc.FIRE


def test_classifier_fails_closed_on_error(monkeypatch):
    def raiser(*args, **kwargs):
        raise RuntimeError("timeout")

    monkeypatch.setattr(oc, "chat", raiser)
    decision = classify_fragment(AMBIGUOUS, SessionState())
    assert decision.fire is False
    assert decision.outcome == oc.FAIL_CLOSED


def test_parse_decision_raises_on_non_json():
    with pytest.raises(ValueError):
        oc._parse_decision("no json here")


# --- Debounce (deterministic, injected decider) ----------------------------------------------

def test_debounce_fires_once_per_utterance():
    calls: list[str] = []

    def always_fire(fragment: str, state: SessionState) -> Decision:
        calls.append(fragment)
        return Decision(True, "leading", "x")

    classifier = ObjectionClassifier(SessionState(), decider=always_fire)

    first = classifier.consider("Isn't it true")
    grown = classifier.consider("Isn't it true that you lied?")   # same utterance, still growing
    again = classifier.consider("Isn't it true that you lied?")   # same again
    new_utterance = classifier.consider("He told me it was red.")  # new utterance re-arms

    assert first.fire is True
    assert grown.fire is False and again.fire is False           # suppressed
    assert new_utterance.fire is True
    # the decider is only invoked when not suppressed
    assert calls == ["Isn't it true", "He told me it was red."]
    assert grown.outcome == oc.DEBOUNCED


# --- Audit outcomes + review log -------------------------------------------------------------

def test_outcomes_are_categorized(monkeypatch):
    # Gate reject (no candidate, no LLM).
    assert (
        classify_fragment("The invoice is dated April 2.", SessionState()).outcome
        == oc.GATE_REJECTED
    )
    # Immediate fire (high-confidence, no LLM) — distinct from an LLM fire.
    assert (
        classify_fragment("Isn't it true you lied?", SessionState()).outcome
        == oc.FIRE_IMMEDIATE
    )
    # LLM fire / no-fire / fail-closed, all on the ambiguous candidate that reaches the model.
    monkeypatch.setattr(oc, "chat", lambda *a, **k: '{"fire": true, "objection_type": "spec"}')
    assert classify_fragment(AMBIGUOUS, SessionState()).outcome == oc.FIRE
    monkeypatch.setattr(oc, "chat", lambda *a, **k: '{"fire": false, "objection_type": null}')
    assert classify_fragment(AMBIGUOUS, SessionState()).outcome == oc.LLM_NO_FIRE

    def raiser(*args, **kwargs):
        raise RuntimeError("timeout")

    monkeypatch.setattr(oc, "chat", raiser)
    assert classify_fragment(AMBIGUOUS, SessionState()).outcome == oc.FAIL_CLOSED


def test_review_log_partitions_gate_immediate_and_llm(monkeypatch):
    # A clean fragment (gate reject), a high-confidence fragment (immediate fire, no LLM), and an
    # ambiguous candidate that reaches the stubbed LLM (no-fire) — each lands in its own partition.
    monkeypatch.setattr(oc, "chat", lambda *a, **k: '{"fire": false, "objection_type": null}')
    classifier = ObjectionClassifier(SessionState(), record=True)
    clean = "The contract was signed on March 3."
    immediate = "Isn't it true you were there?"
    classifier.consider(clean)      # gate reject
    classifier.consider(immediate)  # high-confidence -> immediate fire (no LLM)
    classifier.consider(AMBIGUOUS)  # ambiguous candidate -> LLM no-fire

    assert [r.fragment for r in classifier.gate_rejected()] == [clean]
    assert [r.fragment for r in classifier.immediate_fires()] == [immediate]
    assert [r.fragment for r in classifier.llm_no_fire()] == [AMBIGUOUS]


def test_review_log_off_by_default():
    classifier = ObjectionClassifier(
        SessionState(), decider=lambda f, s: Decision(False, None, "x")
    )
    classifier.consider("The contract was signed on March 3.")
    assert classifier.records == []
