"""
File: agents/objection_harness.py
Purpose: A text-only harness for the objection classifier — no Deepgram / LiveKit. It streams a
    scripted sequence of partial-transcript fragments (clean statements, a growing leading
    question, hearsay, speculation) through ObjectionClassifier and prints the fire/no-fire
    decision for each, so the real-time interrupt logic is fully testable without voice infra.
Depends on: agents/objection_classifier.py, agents/session_state.py (live Fireworks calls for
    gate candidates)
Related: agents/harness.py, docs/ARCHITECTURE.md §6
Security notes: Uses fabricated sample fragments only — never feed real transcript through this
    demo. Requires FIREWORKS_API_KEY for the candidate fragments (clean ones make no API call).
Usage: from agents/, run `python objection_harness.py`.
"""

from __future__ import annotations

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


def main() -> None:
    # record=True keeps a review log so we can inspect what the gate filtered out (testing only).
    classifier = ObjectionClassifier(build_demo_state(), record=True)
    print("Streaming fragments through the objection classifier:\n")
    for fragment in FRAGMENTS:
        decision = classifier.consider(fragment)
        verdict = f"OBJECT ({decision.objection_type})" if decision.fire else "—"
        print(f'[{verdict:>18}]  "{fragment}"')
        print(f"{'':>22}   ({decision.outcome}) {decision.reason}")

    # Review: what the recall-biased gate filtered out, kept separate from LLM no-fire decisions.
    def _review(title: str, records) -> None:
        print(f"\n--- {title} ---")
        for record in records:
            print(f'  "{record.fragment}"')
        if not records:
            print("  (none)")

    _review("Gate-rejected (never reached the LLM)", classifier.gate_rejected())
    _review("LLM no-fire (reached the LLM, judged not to object)", classifier.llm_no_fire())


if __name__ == "__main__":
    main()
