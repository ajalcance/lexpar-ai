"""
File: agents/tests/test_voice_interrupt.py
Purpose: Offline tests for the objection barge-in glue (agents/voice_interrupt.py) — the objection
    utterance text, and that `handle_interim` interrupts + speaks on a fire decision and stays
    silent otherwise. Uses a fake duck-typed session, so no LiveKit / room / mic is involved. (The
    real audio path in main.py can only be verified in a live room.)
Depends on: pytest, asyncio, voice_interrupt, objection_classifier, session_state
"""

import asyncio

from objection_classifier import Decision, ObjectionClassifier
from session_state import SessionState
from voice_interrupt import handle_interim, objection_utterance


class FakeSession:
    """Records interrupt()/say() calls in place of a real AgentSession."""

    def __init__(self):
        self.interrupts = 0
        self.said: list[str] = []

    async def interrupt(self):
        self.interrupts += 1

    async def say(self, text, allow_interruptions=True):
        self.said.append(text)


def test_objection_utterance_from_type():
    def spoken(objection_type):
        return objection_utterance(Decision(True, objection_type, "x", outcome="fire"))

    assert spoken("leading") == "Objection — leading."
    assert spoken("assumes_facts") == "Objection — assumes facts."
    assert spoken(None) == "Objection."
    assert objection_utterance(Decision(False, None, "x")) == ""


def test_handle_interim_barges_in_on_fire():
    session = FakeSession()
    classifier = ObjectionClassifier(
        SessionState(), decider=lambda f, s: Decision(True, "leading", "x", outcome="fire")
    )
    decision = asyncio.run(handle_interim(session, classifier, "Isn't it true you lied?"))
    assert decision.fire is True
    assert session.interrupts == 1
    assert session.said == ["Objection — leading."]


def test_handle_interim_silent_on_no_fire():
    session = FakeSession()
    classifier = ObjectionClassifier(
        SessionState(), decider=lambda f, s: Decision(False, None, "no")
    )
    fragment = "The contract was signed on March 3."
    decision = asyncio.run(handle_interim(session, classifier, fragment))
    assert decision.fire is False
    assert session.interrupts == 0
    assert session.said == []
