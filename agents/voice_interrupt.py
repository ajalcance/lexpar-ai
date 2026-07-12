"""
File: agents/voice_interrupt.py
Purpose: The LiveKit-free glue between the objection classifier and the audio session, so the
    "fire → barge in" wiring is unit-testable without a live room. `handle_interim` takes a
    duck-typed session (anything with async `interrupt()` and `say()`), runs the classifier on a
    transcript fragment off the event loop, and on a fire decision: records the objection into the
    session ledger + appends a `was_interruption` barge-in turn (so the record and the saved
    transcript reflect it), interrupts and speaks the short objection line, publishes the structured
    objection event on the data channel (injected `publish`, Gap 3), and drives the inline Judge
    (injected `judge_rule`) — gating the ruling's audio behind a `wait_for_clear` awaitable so a
    fast ruling on the judge's own track never talks over the still-playing objection line. Stays
    livekit-free: every LiveKit-touching action is an injected callable.
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


def objection_transcript(decision: Decision) -> str:
    """The objection line as recorded in the transcript/report — the terse spoken line PLUS the
    ground's reason (the spoken audio stays short for latency; the written record carries the fuller
    context, matching what the frontend renders live from the structured event)."""
    line = objection_utterance(decision)
    if line and decision.reason:
        return f"{line[:-1]}: {decision.reason}."  # drop the trailing "." then append the reason
    return line


def build_objection_event(decision: Decision) -> dict:
    """The structured event published on the data channel so the frontend can render it (Gap 3)."""
    return {
        "type": "objection",
        "objection_type": decision.objection_type,
        "reason": decision.reason,
        "timestamp": int(time.time() * 1000),
    }


async def handle_interim(
    session,
    classifier: ObjectionClassifier,
    transcript: str,
    publish=None,
    judge_rule=None,
    is_final: bool = False,
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

    `judge_rule` (optional, injected: `async (Objection, str, wait_for_clear) -> None`) is the
    inline judge — it rules on the objection and speaks the ruling right after Opposing Counsel's
    line (main.py wires the real one). `wait_for_clear` is an awaitable the judge MUST await before
    speaking: it resolves when the canned objection line has finished playing. The judge speaks on
    its own participant/track with no shared speech queue, so without this gate a fast ruling would
    talk OVER the objection line. While the judge runs, the classifier is placed on `hold()` so no
    new objection can fire over the judge; the hold is ALWAYS released (success, failure, or
    timeout is the caller's concern — we release on any exit), and the classifier's time-floor
    cooldown still applies after release, so re-arming requires BOTH the ruling to have finished
    AND the floor to have elapsed.
    """
    t_start = time.perf_counter()
    # is_final enables the comparative-grounds fallback for completed finals only (interims stay
    # cheap at the regex gate); passed straight through consider() to the decider.
    decision = await asyncio.to_thread(classifier.consider, transcript, is_final)
    t_decided = time.perf_counter()
    if decision.fire:
        objection = classifier.state.record_objection(
            grounds=decision.objection_type or "objection", raised_by="opposing_counsel"
        )
        classifier.state.add_turn(
            "opposing_counsel", objection_transcript(decision), was_interruption=True
        )
        # force=True: an objection forcibly takes the floor, like in a real courtroom. OC's own
        # counter-argument is now NON-interruptible (allow_interruptions=False), and a plain
        # session.interrupt() RAISES on a non-interruptible speech ("does not allow interruptions",
        # per the SDK) — which crashed the whole barge-in before the canned line, the ruling, or
        # the dispatch log if OC happened to be mid-reply. force bypasses that check.
        await session.interrupt(force=True)
        # Start the ruling NOW (concurrently) so quick_ruling generation OVERLAPS the canned line's
        # playback instead of running after it — otherwise the "Sustained" landed ~2-3s late (canned
        # playback + generation), after the attorney had resumed. The judge speaks on its own
        # participant (no shared queue), so ordering is enforced by the canned_done gate below.
        canned_done = asyncio.Event()
        rule_task = None
        if judge_rule is not None:
            classifier.hold()
            rule_task = asyncio.create_task(
                judge_rule(objection, transcript, canned_done.wait)
            )
        # The objection line is NOT interruptible: it's a ~1-2s canned barge-in ("Objection — X.")
        # that must complete, like the judge's ruling. When it was interruptible, VAD false-
        # positives (echo/noise) cancelled it before one audio frame played — OC went unheard. The
        # judge is already non-interruptible; this makes OC's objection match.
        await session.say(objection_utterance(decision), allow_interruptions=False)
        canned_done.set()  # objection line finished playing — the judge may now speak
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
