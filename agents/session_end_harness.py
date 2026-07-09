"""
File: agents/session_end_harness.py
Purpose: A text-only harness for the end-of-session flow — builds a fake SessionState the way the
    live loop leaves it (attorney turns + recorded, still-PENDING objection barge-ins), then runs
    the judge's end-of-session assessment exactly as main.py does (rule each objection → score +
    weaknesses, extract established facts → strengths, closing ruling), derives the scorecard
    payload, and prints it. If a backend URL + agent token + session id are configured, it also
    POSTs (complete + scorecard) so the full write can be exercised against a running backend.
Depends on: agents/{session_state,judge,scorecard_builder,backend_client}.py, config
Related: agents/main.py (_persist_at_end mirrors this), docs/ARCHITECTURE.md §5/§6.5/§8
Security notes: Uses fabricated sample content only. Needs FIREWORKS_API_KEY for the judge
    assessment; AGENT_SERVICE_TOKEN to actually write.
Usage: from agents/, `python session_end_harness.py` (print only), or set AGENT_SERVICE_TOKEN and
    pass a real session id as argv[1] to write to a running backend.
"""

from __future__ import annotations

import json
import sys

import backend_client
import config
import judge
import scorecard_builder
from session_state import SessionState


def build_demo_state() -> SessionState:
    """A SessionState shaped like the live loop leaves it: attorney turns + recorded barge-in
    objections that are still PENDING (the judge rules on them at session end)."""
    state = SessionState(case_facts="Rivera v. Coastal Logistics: wrongful-termination claim.")
    state.add_turn("attorney", "My client was terminated in retaliation for the safety report.")
    state.add_turn("attorney", "My client told me his supervisor said the report wouldn't matter.")
    state.record_objection("hearsay", "opposing_counsel")
    state.add_turn("opposing_counsel", "Objection — hearsay.", was_interruption=True)
    state.add_turn("attorney", "The contract was signed on March 3, isn't that right?")
    state.record_objection("leading", "opposing_counsel")
    state.add_turn("opposing_counsel", "Objection — leading.", was_interruption=True)
    return state


def apply_assessment(state: SessionState) -> str:
    """The exact end-of-session logic from main.py._persist_at_end: assess, rule, extract facts."""
    assessment = judge.assess_session(state)  # live judge call (fails safe without a key)
    for objection, ruling in zip(state.pending_objections(), assessment["rulings"]):
        try:
            state.rule_on_objection(objection, ruling)
        except ValueError:
            pass
    for fact in assessment["established_facts"]:
        state.add_established_fact(fact)
    return assessment["closing_ruling"]


def main() -> None:
    state = build_demo_state()
    ruling = apply_assessment(state)
    payload = scorecard_builder.build_session_end_payload(state, ruling)

    print("=== After judge assessment ===")
    print("Objections:", [(o.grounds, o.ruling) for o in state.objections])
    print("Established facts:", state.established_facts)
    print("\n=== SCORECARD PAYLOAD (POST /api/sessions/{id}/scorecard) ===")
    print(json.dumps(payload, indent=2))

    session_id = sys.argv[1] if len(sys.argv) > 1 else ""
    if session_id and config.AGENT_SERVICE_TOKEN:
        print(f"\n=== Writing to {config.AGENT_BACKEND_URL} for session {session_id} ===")
        backend_client.complete_session(session_id)
        backend_client.write_scorecard(session_id, payload)
        print("Persisted (session completed + scorecard/transcript written).")
    else:
        print("\n(Print only — set AGENT_SERVICE_TOKEN + pass a session id to write to a backend.)")


if __name__ == "__main__":
    main()
