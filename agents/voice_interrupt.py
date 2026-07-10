"""
File: agents/voice_interrupt.py
Purpose: The LiveKit-free glue between the objection classifier and the audio session, so the
    "fire → barge in" wiring is unit-testable without a live room. `handle_interim` takes a
    duck-typed session (anything with async `interrupt()` and `say()`), runs the classifier on a
    transcript fragment off the event loop, and on a fire decision interrupts and speaks a short
    objection immediately.
Depends on: asyncio; agents/objection_classifier.py (no livekit import)
Related: agents/main.py (wires this into the real AgentSession), docs/ARCHITECTURE.md §6
Security notes: Operates on live transcript fragments (work product) in memory only; the objection
    text it speaks contains no transcript content.
"""

from __future__ import annotations

import asyncio
import logging
import time

from objection_classifier import Decision, ObjectionClassifier

logger = logging.getLogger("lexpar.agents.voice")


def objection_utterance(decision: Decision) -> str:
    """The short line Opposing Counsel barks on a fire decision (kept terse for low-latency)."""
    if not decision.fire:
        return ""
    if decision.objection_type:
        return f"Objection — {decision.objection_type.replace('_', ' ')}."
    return "Objection."


def build_objection_event(decision: Decision) -> dict:
    """The structured event published on the data channel so the frontend can render it (Gap 3)."""
    return {
        "type": "objection",
        "objection_type": decision.objection_type,
        "reason": decision.reason,
        "timestamp": int(time.time() * 1000),
    }


async def handle_interim(
    session, classifier: ObjectionClassifier, transcript: str, publish=None, judge_rule=None
):
    """
    Feed one transcript fragment to the classifier; on a fire decision, barge in — interrupt the
    session and speak the objection immediately, and (if `publish` is provided) emit the structured
    objection event at the same moment so the frontend can show it. `consider` makes a blocking HTTP
    call for gate candidates, so it runs in a worker thread to keep the audio event loop responsive.
    `publish` is injected (an `async (Decision) -> None`) to keep this module livekit-free/testable.
    Returns the decision.

    On a fire it also records the objection into the session ledger and appends a barge-in turn to
    the transcript (via `classifier.state`), so the judge can rule on it and the saved transcript
    shows it — otherwise a spoken objection would leave no trace in the record.

    `judge_rule` (optional, injected: `async (Objection, str) -> None`) is the inline judge — it
    rules on the objection and speaks the ruling right after Opposing Counsel's line (main.py wires
    the real one). While it runs, the classifier is placed on `hold()` so no new objection can fire
    over the judge; the hold is ALWAYS released (success, failure, or timeout is the caller's
    concern — we release on any exit), and the classifier's time-floor cooldown still applies after
    release, so re-arming requires BOTH the ruling to have finished AND the floor to have elapsed.
    """
    t_start = time.perf_counter()
    decision = await asyncio.to_thread(classifier.consider, transcript)
    t_decided = time.perf_counter()
    if decision.fire:
        objection = classifier.state.record_objection(
            grounds=decision.objection_type or "objection", raised_by="opposing_counsel"
        )
        classifier.state.add_turn(
            "opposing_counsel", objection_utterance(decision), was_interruption=True
        )
        await session.interrupt()
        # Start the ruling NOW (concurrently) so quick_ruling generation OVERLAPS the canned line's
        # playback instead of running after it — otherwise the "Sustained" landed ~2-3s late (canned
        # playback + generation), after the attorney had resumed. The ruling's own say() enqueues
        # after the canned line (the SDK serializes the speech queue), so order is preserved.
        rule_task = None
        if judge_rule is not None:
            classifier.hold()
            rule_task = asyncio.create_task(judge_rule(objection, transcript))
        await session.say(objection_utterance(decision), allow_interruptions=True)
        t_said = time.perf_counter()
        # Immediate-fire latency instrumentation (Issue 3): the gate/classify decision and the
        # interrupt+say dispatch. Combine with Deepgram's interim log timestamps + the measured TTS
        # time-to-first-byte for the full "attorney speech → objection audio" breakdown. (Actual
        # first-audio-frame needs deeper TTS hooks; not exposed here.)
        logger.info(
            "objection dispatch [%s/%s]: decide=%.3fs interrupt+say=%.3fs total=%.3fs",
            decision.objection_type,
            decision.outcome,
            t_decided - t_start,
            t_said - t_decided,
            t_said - t_start,
        )
        if publish is not None:
            await publish(decision)
        if rule_task is not None:
            try:
                await rule_task
            finally:
                classifier.release_hold()
    return decision
