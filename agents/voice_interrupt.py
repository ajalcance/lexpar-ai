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

from objection_classifier import Decision, ObjectionClassifier


def objection_utterance(decision: Decision) -> str:
    """The short line Opposing Counsel barks on a fire decision (kept terse for low-latency)."""
    if not decision.fire:
        return ""
    if decision.objection_type:
        return f"Objection — {decision.objection_type.replace('_', ' ')}."
    return "Objection."


async def handle_interim(session, classifier: ObjectionClassifier, transcript: str) -> Decision:
    """
    Feed one transcript fragment to the classifier; on a fire decision, barge in — interrupt the
    session and speak the objection immediately. The classifier's `consider` makes a blocking HTTP
    call for gate candidates, so it runs in a worker thread to keep the audio event loop responsive.
    Returns the decision (for logging/review).
    """
    decision = await asyncio.to_thread(classifier.consider, transcript)
    if decision.fire:
        await session.interrupt()
        await session.say(objection_utterance(decision), allow_interruptions=True)
    return decision
