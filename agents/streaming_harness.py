"""
File: agents/streaming_harness.py
Purpose: Text-only harness for the streaming sentence-level verification pipeline (§6.5) — no
    TTS/audio/LiveKit. Reports the concrete metric TIME TO FIRST VERIFIED SENTENCE (what the
    attorney experiences as first audio), before vs after:
      before = today's blocking path (full reply generation, then one whole-reply verification)
      after  = the streaming pipeline (per-sentence verification, first sentence speaks first)
    Offline mode (default) uses a fake token stream + fake verifier with deterministic delays, and
    also exercises the Option B failure mode (a mid-stream contradiction → one repair) and the
    legal-citation segmentation guard. Live mode (--live) runs the real Fireworks stream + real
    verifier for true wall-clock numbers.
Depends on: agents/streaming_verify.py, agents/session_state.py; --live additionally uses
    agents/{opposing_counsel,verification,harness}.py (live Fireworks calls)
Related: agents/harness.py (the blocking-path harness), docs/ARCHITECTURE.md §6.5
Security notes: Uses fabricated sample case facts only — never feed real attorney data through
    this demo. --live requires FIREWORKS_API_KEY.
Usage: from agents/, run `python streaming_harness.py` (offline) or
    `python streaming_harness.py --live` (real Fireworks calls).
"""

from __future__ import annotations

import sys
import time

from session_state import SessionState
from streaming_verify import stream_verified_reply

# Offline timing model: ~word-sized deltas at TOKEN_DELAY each (a 4-sentence reply ≈ deepseek's
# measured ~2.5-4s full generation), and VERIFY_DELAY per consistency call (gpt-oss on a short
# draft, per the §7 classifier benchmark).
TOKEN_DELAY = 0.05
VERIFY_DELAY = 1.2

CLEAN_REPLY = (
    "Counsel's timeline theory collapses on inspection. "
    "Brown v. Board of Education, 347 U.S. 483 (1954), reminds us that precedent controls "
    "outcomes, not sympathy. "
    "The documented performance issues predate the May 2 report. "
    "Causation is asserted, not proven."
)

# Sentence 2 contradicts the demo record (contract signed March 3) → Option B repair kicks in.
FAILING_REPLY = (
    "The performance file speaks for itself. "
    "The contract was signed on March 15, well before any report. "
    "This later sentence is conditioned on the bad one and must never be spoken."
)
REPAIR_REPLY = "The contract date is not in dispute, and it does not help counsel's theory."


def build_demo_state() -> SessionState:
    state = SessionState(case_facts="Rivera v. Coastal Logistics: wrongful-termination claim.")
    state.add_established_fact("The employment contract was signed on March 3.")
    state.add_established_fact("Plaintiff reported a safety violation on May 2.")
    return state


def fake_stream(text: str):
    """A generation-stream factory that yields word deltas at TOKEN_DELAY, like a live stream."""

    def factory(*_args):
        for word in text.split(" "):
            time.sleep(TOKEN_DELAY)
            yield word + " "

    return factory


def fake_consistency(draft: str, state: SessionState) -> list[str]:
    """Fake verifier at VERIFY_DELAY; flags the scripted contradiction marker."""
    time.sleep(VERIFY_DELAY)
    if "March 15" in draft:
        return ["the record says the contract was signed March 3, not March 15"]
    return []


def run_streaming(
    label: str, state: SessionState, turn: str, generate, repair, consistency
) -> tuple[float, float]:
    """Run the pipeline, printing each verified sentence with its arrival time; return
    (time_to_first_verified_sentence, total_time)."""
    print(f"\n=== {label} ===")
    start = time.perf_counter()
    first: float | None = None
    for sentence in stream_verified_reply(
        state, turn, generate=generate, repair=repair, consistency=consistency
    ):
        elapsed = time.perf_counter() - start
        if first is None:
            first = elapsed
        print(f"  [{elapsed:6.3f}s → TTS] {sentence}")
    total = time.perf_counter() - start
    print(f"  -> first verified sentence {first:.3f}s, reply complete {total:.3f}s")
    return (first if first is not None else total), total


def run_blocking_baseline(label: str, text: str) -> float:
    """Simulate today's blocking path with the same fake timings: consume the full stream, then
    one whole-reply verification. Returns time to first audio (== the whole thing)."""
    state = build_demo_state()
    print(f"\n=== {label} ===")
    start = time.perf_counter()
    reply = "".join(fake_stream(text)(state, "attorney turn")).strip()
    fake_consistency(reply, state)
    elapsed = time.perf_counter() - start
    print(f"  -> first audio only after the full reply + one verification: {elapsed:.3f}s")
    return elapsed


def main_offline() -> None:
    print("Offline mode: deterministic fake stream/verifier "
          f"(token {TOKEN_DELAY * 1000:.0f}ms, verify {VERIFY_DELAY:.1f}s).")

    before = run_blocking_baseline("BEFORE — blocking full reply + whole-reply verify", CLEAN_REPLY)
    after, _total = run_streaming(
        "AFTER — streaming, per-sentence verification (clean reply; citation must not split)",
        build_demo_state(),
        "attorney turn",
        fake_stream(CLEAN_REPLY),
        fake_stream(REPAIR_REPLY),
        fake_consistency,
    )
    run_streaming(
        "Failure mode (Option B) — sentence 2 contradicts the record → one repair continuation",
        build_demo_state(),
        "attorney turn",
        fake_stream(FAILING_REPLY),
        fake_stream(REPAIR_REPLY),
        fake_consistency,
    )

    print("\n=== Time to first verified sentence ===")
    print(f"  before (blocking): {before:.3f}s")
    print(f"  after (streaming): {after:.3f}s")
    print(f"  saved:             {before - after:.3f}s ({(1 - after / before) * 100:.0f}% faster)")


def main_live() -> None:
    import harness  # the blocking-path harness: demo state + attorney turn
    import opposing_counsel
    import verification

    state = harness.build_demo_state()
    turn = harness.ATTORNEY_TURN
    print("Live mode: real Fireworks stream + real verifier.\n")

    print("=== BEFORE — blocking generate_reply + whole-reply check_consistency ===")
    start = time.perf_counter()
    reply = opposing_counsel.generate_reply(state, turn)
    verification.find_suspicious_citations(reply)
    verification.check_consistency(reply, state)
    before = time.perf_counter() - start
    print(f"  -> first audio after {before:.3f}s ({len(reply)} chars)")

    after, total = run_streaming(
        "AFTER — streaming, per-sentence verification (live)",
        harness.build_demo_state(),
        turn,
        opposing_counsel.stream_reply,
        opposing_counsel.stream_continuation,
        verification.check_consistency,
    )

    print("\n=== Time to first verified sentence (live wall clock) ===")
    print(f"  before (blocking): {before:.3f}s")
    print(f"  after (streaming): {after:.3f}s  (full reply spoken by {total:.3f}s)")
    print(f"  saved:             {before - after:.3f}s ({(1 - after / before) * 100:.0f}% faster)")


if __name__ == "__main__":
    if "--live" in sys.argv:
        main_live()
    else:
        main_offline()
