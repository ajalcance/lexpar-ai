"""
File: agents/objection_harness.py
Purpose: A text-only harness for the objection classifier — no Deepgram / LiveKit. It streams a
    scripted sequence of partial-transcript fragments (clean statements, a growing leading
    question, hearsay, speculation) through ObjectionClassifier and prints the fire/no-fire
    decision for each, so the real-time interrupt logic is fully testable without voice infra.
    It also MEASURES latency per fragment and reports a before/after comparison — the two-tier
    gate (high-confidence patterns fire immediately, no LLM) vs. an LLM-only run that simulates the
    pre-two-tier behavior — so the barge-in speedup is measured, not assumed (ARCHITECTURE §6).
    Includes the DOUBLE-FIRE REGRESSION sequence (an STT final revised with smart formatting
    arriving after a pause must NOT re-fire) and an inline-ruling demo (fire → judge rules →
    ledger updated), both deterministic via an injected clock / fake judge. Also demonstrates the
    COMPARATIVE-GROUNDS FALLBACK (Option A): pure relevance / mischaracterization finals (no
    leading/hearsay/speculation/argumentative/CLC surface form) which tier-1 gate-rejects as
    interims but the finals-only fallback routes to tier-3 in oral_argument.
    `_comparative_fallback_demo()` runs each BEFORE (interim → gate-reject, no LLM) and AFTER
    (final → fallback → live model), plus the length-floor skip.
Depends on: agents/objection_classifier.py, agents/session_state.py, agents/voice_interrupt.py
    (live Fireworks calls for ambiguous gate candidates)
Related: agents/harness.py, docs/ARCHITECTURE.md §6, docs/LESSONS.md
Security notes: Uses fabricated sample fragments only — never feed real transcript through this
    demo. Requires FIREWORKS_API_KEY for the ambiguous candidates (clean/high-confidence make no
    API call).
Usage: from agents/, run `python objection_harness.py`.
"""

from __future__ import annotations

import asyncio
import statistics
import time

import objection_classifier as oc
from objection_classifier import ObjectionClassifier
from session_state import SessionState
from voice_interrupt import handle_interim

# Each entry is (seconds_since_previous, fragment) — one partial transcript as it would stream in.
# Utterance 2 grows across three fragments (debounce), utterance 2's FINAL arrives revised by smart
# formatting after a 1s endpointing pause (the double-fire regression), and later utterances arrive
# after realistic >5s gaps so the re-fire cooldown has elapsed.
TIMED_FRAGMENTS = [
    (0.0, "The contract was signed on March 3."),
    (6.0, "now isn't it true"),
    (0.5, "now isn't it true that you never"),
    (0.5, "now isn't it true that you never actually read the contract"),
    # REGRESSION: the segment's final — capitalized + punctuated, same content, 1s pause. The old
    # exact-prefix debounce re-armed on this and double-fired.
    (1.0, "Now, isn't it true that you never actually read the contract?"),
    (7.0, "My neighbor told me the defendant ran the red light."),
    (7.0, "I think the delay was probably intentional."),
    # Piggybacks on the leading recall pattern (trailing "right?", NOT high-confidence), so it
    # reaches tier-3 TODAY regardless of the comparative fallback: it flatly contradicts the
    # established March 3 signing, and with the per-ground reasoning cues the model can recognize
    # the record contradiction. Kept here as the PROMPT-scaffold demo. (The PURE comparative
    # fragments — objectionable only on relevance/mischaracterization with no regex surface form —
    # live in _comparative_fallback_demo() below, where they exercise the finals-only fallback.)
    (7.0, "The contract was signed in June, not March, right?"),
    (6.0, "The invoice is dated April 2."),
]

# PURE comparative-grounds finals for the Option-A fallback demo: objectionable ONLY on relevance /
# mischaracterizes_record, NO leading/hearsay/speculation/argumentative/CLC surface form, so
# candidate_grounds() returns [] — they reach tier-3 solely via the finals fallback (oral_argument).
# The last is under the 8-word length floor and must be skipped without an LLM call.
COMPARATIVE_FINALS = [
    "I'd like to spend some time on the plaintiff's divorce and his gambling debts.",  # relevance
    "The contract was never signed by anyone, so it cannot bind my client.",           # mischar.
    "Frankly, that's irrelevant.",                                                      # < floor
]

# NORMAL oral-argument advocacy that must NOT draw an objection — arguing the law to the bench is
# proper. Before the over-firing fix, the "as a matter of law / the court must find" phrasing fired
# calls_for_legal_conclusion every time (4/4 sustained in the live sessions). It should now decline.
NORMAL_ARGUMENT_FINALS = [
    "As a matter of law, the court should find this mortgage void from its inception.",
    "This court must find that the board's inaction was a breach of fiduciary duty.",
    "The foreclosure proceedings are therefore void for lack of proper authority.",
]


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def build_demo_state() -> SessionState:
    state = SessionState(case_facts="Rivera v. Coastal Logistics: wrongful-termination claim.")
    state.add_established_fact("The employment contract was signed on March 3.")
    return state


def _run(label: str, *, immediate_enabled: bool) -> tuple[ObjectionClassifier, list[float]]:
    """Stream the fragments through a fresh classifier, timing each decision. When
    immediate_enabled is False, the tier-2 immediate-fire shortcut is disabled so every gate
    candidate goes to the LLM — reproducing the pre-two-tier latency for comparison."""
    original = oc.high_confidence_grounds
    if not immediate_enabled:
        oc.high_confidence_grounds = lambda fragment: []  # force all candidates to the LLM
    try:
        clock = FakeClock()
        classifier = ObjectionClassifier(build_demo_state(), record=True, clock=clock)
        latencies: list[float] = []
        print(f"\n=== {label} ===")
        for gap, fragment in TIMED_FRAGMENTS:
            clock.now += gap  # simulated speech pacing (cooldown floor sees realistic gaps)
            t0 = time.perf_counter()
            decision = classifier.consider(fragment)
            dt = time.perf_counter() - t0
            latencies.append(dt)
            verdict = f"OBJECT ({decision.objection_type})" if decision.fire else "—"
            print(
                f"[{verdict:>18}] {dt:6.3f}s  ({decision.outcome:>14}) "
                f'{decision.reason:<34} "{fragment}"'
            )
        print(
            f"  -> median {statistics.median(latencies):.3f}s  total {sum(latencies):.3f}s"
            f"  over {len(latencies)} fragments"
        )
        return classifier, latencies
    finally:
        oc.high_confidence_grounds = original


class _FakeSession:
    async def interrupt(self):
        pass

    async def say(self, text, allow_interruptions=True):
        print(f'    OC speaks: "{text}"')


async def _inline_ruling_demo() -> None:
    """Fire → the (fake, deterministic) judge rules inline → the ledger is updated immediately."""
    print("\n=== Inline judge ruling (deterministic fake judge) ===")
    state = build_demo_state()
    clock = FakeClock()
    classifier = ObjectionClassifier(state, clock=clock)

    async def fake_judge(objection, fragment):
        state.rule_on_objection(objection, "sustained")
        state.add_turn("judge", "Sustained. Classic hearsay.")
        print('    Judge speaks: "Sustained. Classic hearsay."')

    fragment = "He told me the defendant ran the red light."
    print(f'  Attorney: "{fragment}"')
    await handle_interim(_FakeSession(), classifier, fragment, None, fake_judge)
    print(f"  Ledger: {[(o.grounds, o.ruling) for o in state.objections]}")
    print(f"  Transcript: {[(t.speaker, t.content) for t in state.transcript]}")


def _comparative_fallback_demo() -> None:
    """Option A: pure relevance/mischaracterization finals reach tier-3 ONLY via the finals-only
    fallback in oral_argument. Show each fragment BEFORE (as an interim → gate-rejected, no LLM)
    and AFTER (as a final → routed to the live model), plus the length-floor skip. A fresh
    classifier per fragment so the cooldown/debounce of one doesn't mask another (they'd all be
    within the 5s floor otherwise); this demo is about the ROUTE, not the streaming debounce."""
    print("\n=== Comparative-grounds fallback (Option A, oral_argument, live) ===")
    print(f"  (length floor = {oc.FALLBACK_MIN_WORDS} words)\n")
    for fragment in COMPARATIVE_FINALS:
        state = SessionState(proceeding_type="oral_argument")
        state.add_established_fact("The employment contract was signed on March 3.")
        before = ObjectionClassifier(state, clock=FakeClock()).consider(fragment, is_final=False)
        fresh = SessionState(proceeding_type="oral_argument")
        fresh.add_established_fact("The employment contract was signed on March 3.")
        after = ObjectionClassifier(fresh, clock=FakeClock()).consider(fragment, is_final=True)
        b = f"{before.outcome}"
        a = (
            f"OBJECT ({after.objection_type}) [{after.outcome}]"
            if after.fire
            else f"— [{after.outcome}]"
        )
        print(f'  "{fragment}"')
        print(f"      interim(before): {b:<16}   final(after): {a}")

    print("\n  Normal legal argument (must NOT object — arguing the law is proper):")
    for fragment in NORMAL_ARGUMENT_FINALS:
        state = SessionState(proceeding_type="oral_argument")
        decision = ObjectionClassifier(state, clock=FakeClock()).consider(fragment, is_final=True)
        verdict = (
            f"OBJECT ({decision.objection_type}) [{decision.outcome}]"
            if decision.fire
            else f"— no-fire [{decision.outcome}]"
        )
        print(f'  {verdict:<40} "{fragment}"')


def main() -> None:
    # AFTER: the real two-tier gate (high-confidence patterns fire immediately, no LLM).
    two_tier, after = _run("Two-tier gate (immediate-fire on — current)", immediate_enabled=True)
    # BEFORE: force every candidate through the LLM, simulating the pre-two-tier classifier.
    _llm_only, before = _run("LLM-only (simulates pre-two-tier)", immediate_enabled=False)

    print("\n=== Before/after latency ===")
    print(f"  LLM-only (before): total {sum(before):.3f}s  median {statistics.median(before):.3f}s")
    print(f"  Two-tier (after):  total {sum(after):.3f}s  median {statistics.median(after):.3f}s")
    print(f"  Saved:             total {sum(before) - sum(after):.3f}s")

    # Review the two-tier run: what the recall gate filtered, what fired immediately (audit whether
    # the high-confidence gate is too aggressive), and what the LLM judged not to object.
    def _review(title: str, records) -> None:
        print(f"\n--- {title} ---")
        for record in records:
            print(f'  "{record.fragment}"')
        if not records:
            print("  (none)")

    _review("Gate-rejected (never reached the LLM)", two_tier.gate_rejected())
    _review("Immediate fires (high-confidence, no LLM)", two_tier.immediate_fires())
    _review("LLM no-fire (reached the LLM, judged not to object)", two_tier.llm_no_fire())

    _comparative_fallback_demo()
    asyncio.run(_inline_ruling_demo())


if __name__ == "__main__":
    main()
