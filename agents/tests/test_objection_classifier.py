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


# --- Debounce (deterministic, injected decider + clock) --------------------------------------

class FakeClock:
    """Injectable monotonic clock for deterministic cooldown tests."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def always_fire_decider(calls: list[str]):
    def decider(fragment: str, state: SessionState) -> Decision:
        calls.append(fragment)
        return Decision(True, "leading", "x")

    return decider


def test_debounce_fires_once_per_utterance():
    calls: list[str] = []
    clock = FakeClock()
    classifier = ObjectionClassifier(
        SessionState(), decider=always_fire_decider(calls), clock=clock
    )

    first = classifier.consider("Isn't it true")
    grown = classifier.consider("Isn't it true that you lied?")   # same utterance, still growing
    again = classifier.consider("Isn't it true that you lied?")   # same again
    clock.advance(6.0)  # past the re-fire cooldown — genuinely later speech
    new_utterance = classifier.consider("He told me it was red.")  # new utterance re-arms

    assert first.fire is True
    assert grown.fire is False and again.fire is False           # suppressed
    assert new_utterance.fire is True
    # the decider is only invoked when not suppressed
    assert calls == ["Isn't it true", "He told me it was red."]
    assert grown.outcome == oc.DEBOUNCED


def test_revised_final_after_pause_does_not_refire():
    # THE double-fire regression (see PLAN/LESSONS): the STT *final* for an utterance arrives after
    # a pause with smart formatting applied — casing/punctuation changed, same content. It is NOT a
    # string prefix of the last interim, but it must still be treated as the SAME utterance.
    calls: list[str] = []
    clock = FakeClock()
    classifier = ObjectionClassifier(
        SessionState(), decider=always_fire_decider(calls), clock=clock
    )

    interim = classifier.consider("i i my client told me that his supervisor said")
    assert interim.fire is True

    clock.advance(1.0)  # the endpointing pause before the final lands
    revised_final = classifier.consider(
        "I, I, my client told me that his supervisor said the safety report wouldn't matter."
    )
    assert revised_final.fire is False
    assert revised_final.outcome == oc.DEBOUNCED
    assert calls == ["i i my client told me that his supervisor said"]  # LLM never re-consulted


def test_two_hearsay_triggers_across_segment_boundary_fire_once():
    # THE live double-hearsay case: one spoken utterance has two hearsay triggers ("told me" then
    # "said"), and Deepgram (endpointing_ms=25) splits it into two segments. The second segment is
    # NOT a continuation of the first (different words), so debounce alone would re-arm — but it
    # lands inside the re-fire cooldown, so only ONE objection fires.
    calls: list[str] = []
    clock = FakeClock()
    classifier = ObjectionClassifier(
        SessionState(), decider=always_fire_decider(calls), clock=clock
    )

    first = classifier.consider("My client told me")
    clock.advance(0.8)  # brief pause between segments of the same breath
    second = classifier.consider("that his supervisor said the report wouldn't matter")

    assert first.fire is True
    assert second.fire is False
    assert second.outcome == oc.DEBOUNCED
    assert calls == ["My client told me"]  # the second segment never reached the decider


def test_cooldown_suppresses_new_utterance_then_releases():
    # A genuinely NEW objectionable utterance within the cooldown floor is suppressed (no courtroom
    # double-objection seconds after being interrupted); after the floor it fires again.
    calls: list[str] = []
    clock = FakeClock()
    classifier = ObjectionClassifier(
        SessionState(), decider=always_fire_decider(calls), clock=clock
    )

    assert classifier.consider("Isn't it true you lied?").fire is True
    clock.advance(1.0)
    inside_cooldown = classifier.consider("He told me it was red.")
    assert inside_cooldown.fire is False
    assert inside_cooldown.outcome == oc.DEBOUNCED
    assert "cooldown" in inside_cooldown.reason

    clock.advance(5.0)  # 6s total — past the floor
    after_cooldown = classifier.consider("She said that he confessed.")
    assert after_cooldown.fire is True


def test_hold_blocks_refire_until_released_and_floor_elapsed():
    # Re-arming requires BOTH: the ruling hold released AND the time floor elapsed — a slow inline
    # ruling (network jitter) must keep the classifier suppressed past the fixed timer.
    calls: list[str] = []
    clock = FakeClock()
    classifier = ObjectionClassifier(
        SessionState(), decider=always_fire_decider(calls), clock=clock
    )

    assert classifier.consider("Isn't it true you lied?").fire is True
    classifier.hold()  # inline ruling in flight

    clock.advance(10.0)  # floor long elapsed, but the ruling hasn't finished
    held = classifier.consider("He told me it was red.")
    assert held.fire is False
    assert "ruling in progress" in held.reason

    classifier.release_hold()  # ruling finished (floor already elapsed)
    released = classifier.consider("She said that he confessed to it.")
    assert released.fire is True


def test_normalized_continuation_handles_casing_and_punctuation():
    assert ObjectionClassifier._is_continuation(
        "i i my client told me", "I, I, my client told me that his supervisor said"
    )
    assert not ObjectionClassifier._is_continuation(
        "i i my client told me", "The document was never produced."
    )
    assert not ObjectionClassifier._is_continuation("", "anything")


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
    clock = FakeClock()
    classifier = ObjectionClassifier(SessionState(), record=True, clock=clock)
    clean = "The contract was signed on March 3."
    immediate = "Isn't it true you were there?"
    classifier.consider(clean)      # gate reject
    classifier.consider(immediate)  # high-confidence -> immediate fire (no LLM)
    clock.advance(6.0)              # past the re-fire cooldown from the immediate fire
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
