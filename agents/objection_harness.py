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
    ledger updated), both deterministic via an injected clock / fake judge. Also includes
    COMPARATIVE-GROUNDS fragments (relevance / mischaracterizes_record): one that piggybacks into
    tier-3 today via a leading-shaped surface form, and two pure ones that tier-1 GATE-REJECTS
    today (see the fragment comments) — kept in the set so the gate fix, when it lands, has its
    before/after demo ready-made.
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
    # --- Comparative grounds (relevance / mischaracterizes_record) ---------------------------
    # Piggybacks on the leading recall pattern (trailing "right?", NOT high-confidence), so it
    # reaches tier-3 TODAY: it flatly contradicts the established March 3 signing, and with the
    # per-ground reasoning cues the model can recognize the record contradiction — this fragment
    # shows a prompt before/after NOW.
    (7.0, "The contract was signed in June, not March, right?"),
    # PURE relevance — no leading/hearsay/speculation/argumentative/CLC surface form, so tier-1
    # GATE-REJECTS it today (the Finding-1 structural gap): the LLM never sees it regardless of
    # prompt. It demonstrates a before/after only once the comparative-grounds gate fix lands.
    (7.0, "I'd like to spend some time on the plaintiff's divorce and his gambling debts."),
    # PURE mischaracterizes_record — contradicts the established signing with no regex surface
    # form; same GATE-REJECTED-today status as the relevance fragment above.
    (6.0, "The contract was never signed by anyone, so it cannot bind my client."),
    (6.0, "The invoice is dated April 2."),
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

    asyncio.run(_inline_ruling_demo())


if __name__ == "__main__":
    main()
