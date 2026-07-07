"""
File: agents/harness.py
Purpose: A text-only test harness for the agents pipeline — no LiveKit / STT / TTS. It builds a
    fake SessionState (case facts, established facts, a ruled objection), feeds one fake attorney
    transcript turn, generates the Opposing Counsel reply, runs the verification pass (citation
    heuristic + LLM consistency check), and prints everything to the console. Lets the generation +
    verification be exercised end to end while Deepgram/ElevenLabs keys are still unavailable.
Depends on: agents/{session_state,opposing_counsel,judge,verification}.py (live Fireworks calls)
Related: agents/main.py (the eventual real-time entrypoint), docs/ARCHITECTURE.md §6 / §6.5
Security notes: Uses fabricated sample case facts only — never feed real attorney data through this
    demo. Requires FIREWORKS_API_KEY in the environment.
Usage: from agents/, run `python harness.py` (needs a live Fireworks key).
"""

from __future__ import annotations

import judge
import opposing_counsel
import verification
from session_state import SessionState

ATTORNEY_TURN = (
    "Your Honor, my client was terminated in direct retaliation for reporting the safety "
    "violation. The timeline alone makes the causation unmistakable."
)


def build_demo_state() -> SessionState:
    """A small, fabricated session record for the demo."""
    state = SessionState(
        case_facts=(
            "Rivera v. Coastal Logistics: wrongful-termination claim. Plaintiff alleges "
            "retaliation after reporting safety violations; defendant asserts documented "
            "performance issues predating the report."
        )
    )
    state.add_established_fact("Plaintiff reported a safety violation on May 2.")
    state.add_established_fact("Plaintiff was terminated on May 20.")
    objection = state.record_objection("assumes facts not in evidence", "opposing_counsel")
    state.rule_on_objection(objection, "overruled")
    return state


def main() -> None:
    state = build_demo_state()

    print("=== SESSION RECORD ===")
    print(state.snapshot())

    print("\n=== ATTORNEY (fake transcript turn) ===")
    print(ATTORNEY_TURN)

    reply = opposing_counsel.generate_reply(state, ATTORNEY_TURN)
    print("\n=== OPPOSING COUNSEL (Fireworks) ===")
    print(reply)

    suspicious = verification.find_suspicious_citations(reply)
    contradictions = verification.check_consistency(reply, state)
    print("\n=== VERIFICATION PASS ===")
    print("Suspicious citations:", [f.citation for f in suspicious] or "none")
    print("Consistency contradictions:", contradictions or "none")
    print("Verdict:", "REGENERATE" if (suspicious or contradictions) else "PASS → TTS")

    ruling = judge.generate_ruling(state, ATTORNEY_TURN)
    print("\n=== JUDGE (Fireworks) ===")
    print(ruling)


if __name__ == "__main__":
    main()
