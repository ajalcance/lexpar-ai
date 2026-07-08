"""
File: agents/tests/test_objection_classifier.py
Purpose: Offline tests for the objection classifier (ARCHITECTURE §6) — the recall-biased gate on a
    labeled sample set, the fail-closed / short-circuit / parse behavior of classify_fragment (with
    a monkeypatched model call, no network), and the per-utterance debounce. Live model behavior is
    covered in test_live_fireworks.py.
Depends on: pytest, objection_classifier, session_state
"""

import pytest

import objection_classifier as oc
from objection_classifier import (
    Decision,
    ObjectionClassifier,
    candidate_grounds,
    classify_fragment,
)
from session_state import SessionState

# --- Stage 1: recall-biased gate on a labeled sample set -------------------------------------

def test_gate_flags_leading_question():
    assert "leading" in candidate_grounds("Isn't it true that you were there that night?")


def test_gate_flags_tag_question():
    assert "leading" in candidate_grounds("You signed it on the 3rd, didn't you?")


def test_gate_flags_hearsay():
    assert "hearsay" in candidate_grounds("He told me the light was red.")


def test_gate_flags_speculation():
    assert "speculation" in candidate_grounds("I think he probably left early.")


def test_gate_ignores_clean_statement():
    assert candidate_grounds("The contract was signed on March 3.") == []


# --- Stage 2: classify_fragment plumbing (model call monkeypatched — no network) --------------

def test_clean_fragment_short_circuits_without_llm(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("LLM must not be called for a clean fragment")

    monkeypatch.setattr(oc, "chat", boom)
    decision = classify_fragment("The invoice is dated April 2.", SessionState())
    assert decision.fire is False


def test_candidate_fragment_parses_fire(monkeypatch):
    monkeypatch.setattr(
        oc,
        "chat",
        lambda *a, **k: '{"fire": true, "objection_type": "Leading", "reason": "tag question"}',
    )
    decision = classify_fragment("Isn't it true you lied?", SessionState())
    assert decision.fire is True
    assert decision.objection_type == "leading"


def test_classifier_fails_closed_on_error(monkeypatch):
    def raiser(*args, **kwargs):
        raise RuntimeError("timeout")

    monkeypatch.setattr(oc, "chat", raiser)
    decision = classify_fragment("Isn't it true you lied?", SessionState())
    assert decision.fire is False


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
    assert (
        classify_fragment("The invoice is dated April 2.", SessionState()).outcome
        == oc.GATE_REJECTED
    )
    monkeypatch.setattr(oc, "chat", lambda *a, **k: '{"fire": true, "objection_type": "leading"}')
    assert classify_fragment("Isn't it true you lied?", SessionState()).outcome == oc.FIRE
    monkeypatch.setattr(oc, "chat", lambda *a, **k: '{"fire": false, "objection_type": null}')
    assert classify_fragment("Isn't it true you lied?", SessionState()).outcome == oc.LLM_NO_FIRE

    def raiser(*args, **kwargs):
        raise RuntimeError("timeout")

    monkeypatch.setattr(oc, "chat", raiser)
    assert classify_fragment("Isn't it true you lied?", SessionState()).outcome == oc.FAIL_CLOSED


def test_review_log_partitions_gate_vs_llm(monkeypatch):
    # Candidate fragments reach the (stubbed) LLM, which declines; clean fragments never do.
    monkeypatch.setattr(oc, "chat", lambda *a, **k: '{"fire": false, "objection_type": null}')
    classifier = ObjectionClassifier(SessionState(), record=True)
    clean = "The contract was signed on March 3."
    candidate = "Isn't it true you were there?"
    classifier.consider(clean)      # gate reject
    classifier.consider(candidate)  # candidate -> LLM no-fire

    assert [r.fragment for r in classifier.gate_rejected()] == [clean]
    assert [r.fragment for r in classifier.llm_no_fire()] == [candidate]


def test_review_log_off_by_default():
    classifier = ObjectionClassifier(
        SessionState(), decider=lambda f, s: Decision(False, None, "x")
    )
    classifier.consider("The contract was signed on March 3.")
    assert classifier.records == []
