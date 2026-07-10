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
from voice_interrupt import build_objection_event, handle_interim, objection_utterance


class FakeSession:
    """Records interrupt()/say() calls in place of a real AgentSession."""

    def __init__(self):
        self.interrupts = 0
        self.said: list[str] = []

    async def interrupt(self):
        self.interrupts += 1

    async def say(self, text, allow_interruptions=True):
        self.said.append(text)


class FakePublisher:
    """Records the decisions published to the data channel."""

    def __init__(self):
        self.published: list[Decision] = []

    async def __call__(self, decision):
        self.published.append(decision)


def test_build_objection_event_shape():
    event = build_objection_event(Decision(True, "leading", "tag question", outcome="fire"))
    assert event["type"] == "objection"
    assert event["objection_type"] == "leading"
    assert event["reason"] == "tag question"
    assert isinstance(event["timestamp"], int)


def test_objection_utterance_from_type():
    def spoken(objection_type):
        return objection_utterance(Decision(True, objection_type, "x", outcome="fire"))

    assert spoken("leading") == "Objection — leading."
    assert spoken("assumes_facts") == "Objection — assumes facts."
    assert spoken(None) == "Objection."
    assert objection_utterance(Decision(False, None, "x")) == ""


def test_handle_interim_barges_in_and_publishes_on_fire():
    session = FakeSession()
    publisher = FakePublisher()
    state = SessionState()
    classifier = ObjectionClassifier(
        state, decider=lambda f, s: Decision(True, "leading", "x", outcome="fire")
    )
    decision = asyncio.run(
        handle_interim(session, classifier, "Isn't it true you lied?", publisher)
    )
    assert decision.fire is True
    assert session.interrupts == 1
    assert session.said == ["Objection — leading."]
    assert publisher.published == [decision]  # event published at the barge-in moment
    # The fire is recorded in the ledger (pending, for the judge to rule on) and shows in the
    # transcript as a barge-in turn — otherwise the spoken objection leaves no trace.
    assert len(state.objections) == 1
    assert state.objections[0].grounds == "leading"
    assert state.objections[0].raised_by == "opposing_counsel"
    assert state.objections[0].ruling == "pending"
    assert len(state.transcript) == 1
    assert state.transcript[0].speaker == "opposing_counsel"
    assert state.transcript[0].was_interruption is True
    assert state.transcript[0].content == "Objection — leading."


def test_handle_interim_silent_and_no_publish_on_no_fire():
    session = FakeSession()
    publisher = FakePublisher()
    state = SessionState()
    classifier = ObjectionClassifier(
        state, decider=lambda f, s: Decision(False, None, "no")
    )
    fragment = "The contract was signed on March 3."
    decision = asyncio.run(handle_interim(session, classifier, fragment, publisher))
    assert decision.fire is False
    assert session.interrupts == 0
    assert session.said == []
    assert publisher.published == []
    assert state.objections == []  # nothing recorded when no objection fires
    assert state.transcript == []


def test_handle_interim_records_generic_objection_when_type_missing():
    session = FakeSession()
    state = SessionState()
    classifier = ObjectionClassifier(
        state, decider=lambda f, s: Decision(True, None, "x", outcome="fire")
    )
    asyncio.run(handle_interim(session, classifier, "some fragment", None))
    assert state.objections[0].grounds == "objection"  # falls back when type is None
    assert session.said == ["Objection."]


# --- Inline judge ruling (judge_rule injectable) ----------------------------------------------

class FakeJudge:
    """Records judge_rule calls; optionally raises to exercise the hold-release guarantee."""

    def __init__(self, raises: bool = False):
        self.calls: list[tuple] = []
        self.raises = raises

    async def __call__(self, objection, fragment):
        self.calls.append((objection, fragment))
        if self.raises:
            raise RuntimeError("ruling model down")


def test_judge_rule_called_with_recorded_objection_on_fire():
    session = FakeSession()
    state = SessionState()
    judge = FakeJudge()
    classifier = ObjectionClassifier(
        state, decider=lambda f, s: Decision(True, "hearsay", "x", outcome="fire")
    )
    asyncio.run(handle_interim(session, classifier, "He told me it was red.", None, judge))
    assert len(judge.calls) == 1
    objection, fragment = judge.calls[0]
    assert objection is state.objections[0]  # the exact ledger entry, so rule_on_objection works
    assert fragment == "He told me it was red."
    assert not classifier._held  # hold released after the ruling completed


def test_judge_rule_not_called_on_no_fire():
    session = FakeSession()
    judge = FakeJudge()
    classifier = ObjectionClassifier(
        SessionState(), decider=lambda f, s: Decision(False, None, "no")
    )
    asyncio.run(handle_interim(session, classifier, "The invoice is dated April 2.", None, judge))
    assert judge.calls == []
    assert not classifier._held


def test_canned_objection_dispatched_before_ruling_runs():
    # Ordering guarantee behind the concurrency fix: the ruling task runs while/after the canned
    # line is dispatched (so quick_ruling overlaps its playback), and the canned line is always
    # spoken first — the ruling's say enqueues after it.
    session = FakeSession()
    state = SessionState()
    said_when_judge_ran: dict = {}

    async def judge(objection, fragment):
        said_when_judge_ran["said"] = list(session.said)

    classifier = ObjectionClassifier(
        state, decider=lambda f, s: Decision(True, "leading", "x", outcome="fire")
    )
    asyncio.run(handle_interim(session, classifier, "Isn't it true you lied?", None, judge))
    assert said_when_judge_ran["said"] == ["Objection — leading."]


def test_hold_released_even_when_judge_rule_raises():
    session = FakeSession()
    state = SessionState()
    judge = FakeJudge(raises=True)
    classifier = ObjectionClassifier(
        state, decider=lambda f, s: Decision(True, "leading", "x", outcome="fire")
    )
    try:
        asyncio.run(handle_interim(session, classifier, "Isn't it true?", None, judge))
    except RuntimeError:
        pass  # main.py's judge_rule catches internally; the glue must still release the hold
    assert not classifier._held  # a failed ruling must never leave the classifier locked
