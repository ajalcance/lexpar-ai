"""
File: agents/session_end_harness.py
Purpose: A text-only harness for the Gap 4 session-end persistence — builds a fake SessionState with
    turns/facts/objections, derives the scorecard payload the worker would send, and prints it. If a
    backend URL + agent token + session id are configured, it also POSTs (complete + scorecard) so
    the full write can be exercised against a running backend. Offline by default (just prints).
Depends on: agents/{session_state,scorecard_builder,backend_client}.py, config
Related: docs/ARCHITECTURE.md §5/§8
Security notes: Uses fabricated sample content only. Requires AGENT_SERVICE_TOKEN to actually write.
Usage: from agents/, `python session_end_harness.py` (print only), or set AGENT_SERVICE_TOKEN and
    pass a real session id as argv[1] to write to a running backend.
"""

from __future__ import annotations

import json
import sys

import backend_client
import config
import scorecard_builder
from session_state import SessionState

RULING = "The good-faith argument is viable but was undercut by an early misstep on the record."


def build_demo_state() -> SessionState:
    state = SessionState(case_facts="Rivera v. Coastal Logistics: wrongful-termination claim.")
    state.add_established_fact("Plaintiff reported a safety violation on May 2.")
    state.add_established_fact("Plaintiff was terminated on May 20.")
    objection = state.record_objection("hearsay", "opposing_counsel")
    state.rule_on_objection(objection, "sustained")
    state.add_turn("attorney", "My client was terminated in retaliation for the safety report.")
    state.add_turn("opposing_counsel", "Objection — hearsay.", was_interruption=True)
    state.add_turn("judge", "Sustained. Confine yourself to the record.")
    return state


def main() -> None:
    state = build_demo_state()
    payload = scorecard_builder.build_session_end_payload(state, RULING)

    print("=== SCORECARD PAYLOAD (POST /api/sessions/{id}/scorecard) ===")
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
