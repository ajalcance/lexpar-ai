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
    # Injected deciders match classify_fragment's contract, which now takes a keyword-only
    # is_final (consider() passes it through); the fake ignores it.
    def decider(fragment: str, state: SessionState, *, is_final: bool = False) -> Decision:
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
    # (The fired type must be a REAL taxonomy ground — an unknown/ineligible type is now
    # suppressed by the §13 eligibility guard, tested separately in test_court_knowledge.py.)
    monkeypatch.setattr(
        oc, "chat", lambda *a, **k: '{"fire": true, "objection_type": "speculation"}'
    )
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
        SessionState(), decider=lambda f, s, **_: Decision(False, None, "x")
    )
    classifier.consider("The contract was signed on March 3.")
    assert classifier.records == []


# --- §13: taxonomy expansion + proceeding-type eligibility mapping (constants; wiring = Phase 4) --

def test_taxonomy_includes_argument_grounds():
    for ground in ("relevance", "mischaracterizes_record", "calls_for_legal_conclusion"):
        assert ground in oc.OBJECTION_TYPES
    # the original five remain
    for ground in ("leading", "hearsay", "speculation", "argumentative", "assumes_facts"):
        assert ground in oc.OBJECTION_TYPES


def test_eligible_grounds_cover_every_proceeding_type_and_only_known_grounds():
    # Keys must match backend/app/models/session.py PROCEEDING_TYPES (no shared import — pinned).
    assert set(oc.PROCEEDING_ELIGIBLE_GROUNDS) == {
        "oral_argument",
        "direct_examination",
        "cross_examination",
        "motion_hearing",
    }
    for grounds in oc.PROCEEDING_ELIGIBLE_GROUNDS.values():
        assert grounds  # no proceeding type is left with zero eligible grounds
        assert set(grounds) <= set(oc.OBJECTION_TYPES)


def test_witness_grounds_not_eligible_in_argument_proceedings():
    # The audit-flagged mismatch: no witness in argument → leading/hearsay/speculation
    # are procedurally incoherent there.
    for proceeding in ("oral_argument", "motion_hearing"):
        grounds = set(oc.PROCEEDING_ELIGIBLE_GROUNDS[proceeding])
        assert not grounds & {"leading", "hearsay", "speculation", "argumentative"}


def test_leading_eligible_only_on_direct_examination():
    assert "leading" in oc.PROCEEDING_ELIGIBLE_GROUNDS["direct_examination"]
    # Leading questions are generally permitted on cross — not an eligible ground there.
    assert "leading" not in oc.PROCEEDING_ELIGIBLE_GROUNDS["cross_examination"]


# --- §13 Phase 4: proceeding-type gating at every tier ---------------------------------------

def _oral_argument_state() -> SessionState:
    return SessionState(case_facts="F", proceeding_type="oral_argument")


def test_gate_filters_ineligible_grounds_before_any_tier(monkeypatch):
    # The audit-flagged mismatch: a trailing "?" gates `leading`, which is procedurally
    # incoherent in oral argument — it must die at the gate, reaching neither tier 2 nor the LLM.
    def boom(*args, **kwargs):
        raise AssertionError("LLM must not be called for an ineligible-only candidate")

    monkeypatch.setattr(oc, "chat", boom)
    decision = classify_fragment("Where was the witness that night?", _oral_argument_state())
    assert decision.outcome == oc.GATE_REJECTED
    assert not decision.fire
    assert "ineligible" in decision.reason


def test_high_confidence_leading_cannot_fire_in_oral_argument(monkeypatch):
    # Tier-2's strongest leading pattern: immediate fire on direct, filtered in argument.
    fragment = "Isn't it true you were there?"
    assert (
        classify_fragment(
            fragment, SessionState(proceeding_type="direct_examination")
        ).outcome
        == oc.FIRE_IMMEDIATE
    )
    monkeypatch.setattr(oc, "chat", boom_llm := (lambda *a, **k: '{"fire": false}'))
    del boom_llm
    decision = classify_fragment(fragment, _oral_argument_state())
    assert decision.outcome == oc.GATE_REJECTED  # leading was its only candidate ground


def test_eligible_candidates_still_reach_llm_in_oral_argument(monkeypatch):
    captured: dict = {}

    def fake_chat(endpoint, messages, **kwargs):
        captured["messages"] = messages
        return '{"fire": true, "objection_type": "calls_for_legal_conclusion", "reason": "r"}'

    monkeypatch.setattr(oc, "chat", fake_chat)
    decision = classify_fragment(
        "As a matter of law, this amounts to bad faith.", _oral_argument_state()
    )
    assert decision.fire and decision.objection_type == "calls_for_legal_conclusion"
    system = captured["messages"][0]["content"]
    # The valid-type list OFFERED to the model is narrowed to the eligible grounds. (The prompt's
    # per-ground reasoning cues deliberately describe ALL grounds — they are recognition patterns,
    # explicitly subordinated to the Valid-types line — so narrowing is asserted on the offer line
    # itself, not on whole-prompt name absence; the post-parse guard for a disobedient fire is
    # covered by test_llm_fire_with_ineligible_type_is_suppressed.)
    assert (
        "Valid objection types: relevance, assumes_facts, mischaracterizes_record, "
        "calls_for_legal_conclusion. objection_type MUST be one of these or null." in system
    )
    # and the proceeding type is stated in the user content
    assert "PROCEEDING TYPE: oral_argument" in captured["messages"][1]["content"]


def test_llm_fire_with_ineligible_type_is_suppressed(monkeypatch):
    # Belt-and-braces: even if the model ignores the narrowed list, an ineligible/unknown type
    # never fires.
    monkeypatch.setattr(
        oc, "chat", lambda *a, **k: '{"fire": true, "objection_type": "hearsay", "reason": "r"}'
    )
    decision = classify_fragment(
        "As a matter of law, this amounts to bad faith.", _oral_argument_state()
    )
    assert not decision.fire
    assert decision.outcome == oc.LLM_NO_FIRE
    assert "ineligible" in decision.reason


def test_unknown_or_empty_proceeding_type_fails_open_to_all_grounds():
    assert oc.eligible_grounds_for("") == oc.OBJECTION_TYPES
    assert oc.eligible_grounds_for("bench_trial") == oc.OBJECTION_TYPES
    assert oc.eligible_grounds_for("oral_argument") == oc.PROCEEDING_ELIGIBLE_GROUNDS[
        "oral_argument"
    ]


def test_legal_conclusion_gate_patterns_are_candidates_not_immediate():
    fragment = "The court should find that the transfer was void."
    assert "calls_for_legal_conclusion" in candidate_grounds(fragment)
    assert high_confidence_grounds(fragment) == []  # judgment call — never fires without the LLM


# --- Comparative-grounds fallback (Option A) -----------------------------------------------------
# A pure relevance/mischaracterization statement: no leading/hearsay/speculation/argumentative/CLC
# surface form, so candidate_grounds() returns []. It reaches tier-3 ONLY via the finals fallback.
PURE_COMPARATIVE = "The contract was never signed by anyone, so it cannot bind my client."


def _fire_chat(*a, **k):
    return (
        '{"fire": true, "objection_type": "mischaracterizes_record", "reason": "misstates record"}'
    )


def test_pure_comparative_has_no_regex_candidate():
    assert candidate_grounds(PURE_COMPARATIVE) == []  # the precondition the fallback exists for


def test_final_routes_pure_comparative_to_tier3(monkeypatch):
    captured: dict = {}

    def fake_chat(endpoint, messages, **kwargs):
        captured["messages"] = messages
        return _fire_chat()

    monkeypatch.setattr(oc, "chat", fake_chat)
    decision = classify_fragment(PURE_COMPARATIVE, _oral_argument_state(), is_final=True)
    assert decision.fire and decision.objection_type == "mischaracterizes_record"
    assert decision.outcome == oc.FALLBACK_FIRE  # its own audit outcome, not plain FIRE
    # the comparative grounds (no regex) were offered as the candidate hint
    assert "HEURISTIC CANDIDATES: relevance, assumes_facts, mischaracterizes_record" in (
        captured["messages"][1]["content"]
    )


def test_interim_does_not_trigger_fallback(monkeypatch):
    # Same fragment, but as an INTERIM (is_final=False, the default) — must gate-reject, never call
    # the model. Interims staying cheap at the regex gate is the whole point of finals-only.
    monkeypatch.setattr(oc, "chat", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no LLM")))
    decision = classify_fragment(PURE_COMPARATIVE, _oral_argument_state(), is_final=False)
    assert decision.outcome == oc.GATE_REJECTED and not decision.fire


def test_fallback_no_fire_when_model_declines(monkeypatch):
    monkeypatch.setattr(oc, "chat", lambda *a, **k: '{"fire": false}')
    decision = classify_fragment(PURE_COMPARATIVE, _oral_argument_state(), is_final=True)
    assert not decision.fire and decision.outcome == oc.FALLBACK_NO_FIRE


def test_fallback_off_in_witness_examination(monkeypatch):
    # direct/cross-exam have witness grounds eligible → the fallback stays off (those grounds
    # already reach tier-3 by regex; the fallback would only flood examination turns). No LLM call.
    monkeypatch.setattr(oc, "chat", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no LLM")))
    for pt in ("direct_examination", "cross_examination"):
        decision = classify_fragment(
            PURE_COMPARATIVE, SessionState(proceeding_type=pt), is_final=True
        )
        assert decision.outcome == oc.GATE_REJECTED, pt


def test_fallback_off_for_unknown_proceeding(monkeypatch):
    # Empty/unknown proceeding fails open to ALL grounds (witness grounds present) → fallback off,
    # so offline harnesses/tests with no proceeding type never trigger LLM calls on plain sentences.
    monkeypatch.setattr(oc, "chat", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no LLM")))
    decision = classify_fragment(PURE_COMPARATIVE, SessionState(), is_final=True)
    assert decision.outcome == oc.GATE_REJECTED


def test_fallback_length_floor_skips_trivial_final(monkeypatch):
    monkeypatch.setattr(oc, "chat", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no LLM")))
    decision = classify_fragment(
        "Frankly, that's irrelevant.", _oral_argument_state(), is_final=True
    )
    assert decision.outcome == oc.GATE_REJECTED  # under FALLBACK_MIN_WORDS → no LLM


def test_motion_hearing_also_gets_the_fallback(monkeypatch):
    monkeypatch.setattr(oc, "chat", _fire_chat)
    decision = classify_fragment(
        PURE_COMPARATIVE, SessionState(proceeding_type="motion_hearing"), is_final=True
    )
    assert decision.outcome == oc.FALLBACK_FIRE


def test_fallback_fire_is_debounced_and_cooled_through_consider(monkeypatch):
    # A fallback fire flows through consider() like any fire: it latches _handled (a continuation
    # final is deduped) and starts the cooldown (a new comparative final inside the floor is
    # suppressed) — reusing the SAME machinery the always_fire regression tests cover, driven here
    # by a real fallback fire rather than a fake decider.
    monkeypatch.setattr(oc, "chat", _fire_chat)
    clock = FakeClock()
    classifier = ObjectionClassifier(_oral_argument_state(), record=True, clock=clock)
    first = classifier.consider(PURE_COMPARATIVE, is_final=True)
    assert first.fire and first.outcome == oc.FALLBACK_FIRE
    # same utterance continuing (final revised) → debounced, not a second fire
    grown = classifier.consider(PURE_COMPARATIVE + " Indeed.", is_final=True)
    assert grown.outcome == oc.DEBOUNCED
    # a genuinely new comparative final within the cooldown floor → suppressed by the time floor
    clock.now += 1.0
    other = classifier.consider(
        "Counsel's argument wanders far outside anything this dispute puts in issue.", is_final=True
    )
    assert other.outcome == oc.DEBOUNCED
    # and the review partition surfaces the fallback route on its own
    assert [r.fragment for r in classifier.comparative_fallback()] == [PURE_COMPARATIVE]
