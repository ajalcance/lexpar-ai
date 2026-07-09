"""
File: agents/objection_harness.py
Purpose: A text-only harness for the objection classifier — no Deepgram / LiveKit. It streams a
    scripted sequence of partial-transcript fragments (clean statements, a growing leading
    question, hearsay, speculation) through ObjectionClassifier and prints the fire/no-fire
    decision for each, so the real-time interrupt logic is fully testable without voice infra.
    It also MEASURES latency per fragment and reports a before/after comparison — the two-tier
    gate (high-confidence patterns fire immediately, no LLM) vs. an LLM-only run that simulates the
    pre-two-tier behavior — so the barge-in speedup is measured, not assumed (ARCHITECTURE §6).
Depends on: agents/objection_classifier.py, agents/session_state.py (live Fireworks calls for
    ambiguous gate candidates)
Related: agents/harness.py, docs/ARCHITECTURE.md §6, docs/LESSONS.md
Security notes: Uses fabricated sample fragments only — never feed real transcript through this
    demo. Requires FIREWORKS_API_KEY for the ambiguous candidates (clean/high-confidence make no
    API call).
Usage: from agents/, run `python objection_harness.py`.
"""

from __future__ import annotations

import statistics
import time

import objection_classifier as oc
from objection_classifier import ObjectionClassifier
from session_state import SessionState

# Each line is one partial-transcript fragment as it would stream in. The middle three grow the
# SAME leading-question utterance to show debounce (fire once, then suppressed).
FRAGMENTS = [
    "The contract was signed on March 3.",
    "Now, isn't it true",
    "Now, isn't it true that you never",
    "Now, isn't it true that you never actually read the contract?",
    "Now, isn't it true that you never actually read the contract?",
    "My neighbor told me the defendant ran the red light.",
    "I think the delay was probably intentional.",
    "The invoice is dated April 2.",
]


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
        classifier = ObjectionClassifier(build_demo_state(), record=True)
        latencies: list[float] = []
        print(f"\n=== {label} ===")
        for fragment in FRAGMENTS:
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


if __name__ == "__main__":
    main()
