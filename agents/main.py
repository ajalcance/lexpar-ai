"""
File: agents/main.py
Purpose: The real LiveKit Agents worker (ARCHITECTURE §6). Joins a session's room and runs the
    voice pipeline: Deepgram streaming STT → Opposing Counsel (Fireworks, via opposing_counsel.py)
    → verification pass → ElevenLabs Flash TTS, with Silero VAD + turn detection. The objection
    classifier watches interim transcripts and, on a "fire" decision, barges in: it interrupts the
    in-progress turn and Opposing Counsel objects immediately (LiveKit's built-in interruption).
    opposing_counsel.py / judge.py / verification.py are used verbatim — this file only connects the
    audio layer around them.
Depends on: livekit-agents + plugins (see requirements-voice.txt); config, opposing_counsel, judge,
    verification, objection_classifier, session_state, voice_interrupt
Related: backend/app/api/livekit_token.py (issues the room token), agents/voice_interrupt.py,
    docs/ARCHITECTURE.md §6 / §6.5 / §10
Security notes: Handles live attorney audio + transcripts (work product). Never log raw transcript
    content; persist only through the backend models. Provider keys come from the environment.

⚠️ NOT verifiable without a live LiveKit room + a real microphone. Written to the livekit-agents 1.x
API (AgentSession / session.on("user_input_transcribed") / session.interrupt() / session.say()); the
exact llm_node signature and event fields may need tuning against the installed SDK in a running
room. The livekit-free wiring lives in voice_interrupt.py and is unit-tested; this file is not
imported by the test suite.

Run (needs a running LiveKit server + keys in .env):
    pip install -r agents/requirements-voice.txt
    python agents/main.py dev
"""

from __future__ import annotations

import asyncio
import json
import logging

from livekit import agents
from livekit.agents import Agent, AgentSession, WorkerOptions, cli
from livekit.plugins import deepgram, elevenlabs, openai, silero

import backend_client
import config
import judge
import opposing_counsel
import scorecard_builder
import verification
from objection_classifier import ObjectionClassifier
from session_state import SessionState
from voice_interrupt import build_objection_event, handle_interim

logger = logging.getLogger("lexpar.agents")

# Bounded regenerate loop for the pre-TTS verification pass (ARCHITECTURE §6.5).
MAX_VERIFICATION_RETRIES = 2


def _session_id_from_room(room) -> str:
    """The backend session id is encoded in the room name (livekit_token.py: 'session-<id>')."""
    return (getattr(room, "name", "") or "").removeprefix("session-")


def _last_user_text(chat_ctx) -> str:
    """Best-effort extraction of the attorney's latest utterance from the chat context."""
    for item in reversed(getattr(chat_ctx, "items", [])):
        if getattr(item, "role", None) == "user":
            return getattr(item, "text_content", "") or ""
    return ""


class OpposingCounselAgent(Agent):
    """
    Opposing Counsel routed into LiveKit. The persona + generation live in opposing_counsel.py and
    the verification pass in verification.py (both unchanged); this overrides the LLM step so the
    pipeline speaks *our* verified reply instead of a stock model completion.
    """

    def __init__(self, state: SessionState):
        super().__init__(instructions="You are opposing counsel in a courtroom rehearsal session.")
        self._state = state

    async def llm_node(self, chat_ctx, tools, model_settings):
        attorney_turn = _last_user_text(chat_ctx)
        # generate_reply + verification are blocking (Fireworks HTTP); run off the event loop.
        reply = await asyncio.to_thread(self._verified_reply, attorney_turn)
        self._state.add_turn("opposing_counsel", reply)  # accumulate for the end-of-session batch
        yield reply

    def _verified_reply(self, attorney_turn: str) -> str:
        """Generate, then run the §6.5 verification pass; regenerate a bounded number of times."""
        reply = opposing_counsel.generate_reply(self._state, attorney_turn)
        for _ in range(MAX_VERIFICATION_RETRIES):
            suspicious = verification.find_suspicious_citations(reply)
            contradictions = verification.check_consistency(reply, self._state)
            if not suspicious and not contradictions:
                break
            reply = opposing_counsel.generate_reply(self._state, attorney_turn)
        return reply


async def entrypoint(ctx: agents.JobContext) -> None:
    await ctx.connect()

    # TODO(backend): load the session's case_facts (and prior established facts) for this room from
    # the backend so SessionState reflects the real case. Empty state is fine for a first bring-up.
    state = SessionState()
    classifier = ObjectionClassifier(state)
    last_turn = {"text": ""}

    session = AgentSession(
        vad=silero.VAD.load(),
        stt=deepgram.STT(model=config.DEEPGRAM_MODEL, interim_results=True),
        # The pipeline requires an llm; OpposingCounselAgent.llm_node overrides how it is used.
        llm=openai.LLM(
            model=config.OPPOSING_COUNSEL_MODEL,
            base_url=config.OPPOSING_COUNSEL_ENDPOINT,
            api_key=config.FIREWORKS_API_KEY,
        ),
        tts=elevenlabs.TTS(
            model=config.ELEVENLABS_MODEL,
            voice_id=config.ELEVENLABS_VOICE_ID,
        ),
    )

    async def publish_objection(decision) -> None:
        # Gap 3: emit the structured objection event on the data channel at the barge-in moment so
        # the frontend can render it. reliable=True so it isn't dropped. (livekit-rtc signature —
        # topic/reliable may need tuning against the installed SDK in a live room.)
        event = build_objection_event(decision)
        await ctx.room.local_participant.publish_data(
            json.dumps(event).encode("utf-8"), reliable=True, topic="objection"
        )

    @session.on("user_input_transcribed")
    def _on_user_transcript(event) -> None:
        # Every interim/final fragment feeds the objection classifier; a fire barges in via the
        # tested voice_interrupt glue (the classifier debounces so a growing fragment won't refire).
        if getattr(event, "is_final", False):
            last_turn["text"] = event.transcript
            state.add_turn("attorney", event.transcript)  # accumulate the attorney's turn
        coro = handle_interim(session, classifier, event.transcript, publish_objection)
        asyncio.create_task(coro)

    async def _persist_at_end() -> None:
        # Session end (Gap 4): Judge's closing ruling (judge.py unchanged), then ONE batch write —
        # complete the session and persist the transcript + a scorecard derived from the ruling +
        # SessionState, using the scoped agent service token.
        if not last_turn["text"]:
            return
        ruling = await asyncio.to_thread(judge.generate_ruling, state, last_turn["text"])
        state.add_turn("judge", ruling)
        session_id = _session_id_from_room(ctx.room)
        payload = scorecard_builder.build_session_end_payload(state, ruling)
        turn_count = len(state.transcript)
        try:
            await asyncio.to_thread(backend_client.complete_session, session_id)
            await asyncio.to_thread(backend_client.write_scorecard, session_id, payload)
            logger.info("Persisted session %s (scorecard + %d turns)", session_id, turn_count)
        except Exception:
            logger.exception("Failed to persist session %s at shutdown", session_id)

    ctx.add_shutdown_callback(_persist_at_end)

    await session.start(agent=OpposingCounselAgent(state), room=ctx.room)


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
