"""
File: agents/main.py
Purpose: The real LiveKit Agents worker (ARCHITECTURE §6). Joins a session's room and runs the
    voice pipeline: Deepgram streaming STT → Opposing Counsel (Fireworks, via opposing_counsel.py)
    → streaming sentence-level verification (§6.5, streaming_verify.py) → ElevenLabs Flash TTS,
    with Silero VAD + turn detection. Replies are streamed and verified sentence-by-sentence, so
    TTS starts on the first verified sentence while the rest is still generating — nothing
    unverified is ever spoken. The objection classifier watches interim transcripts and, on a
    "fire" decision, barges in: it interrupts the in-progress turn and Opposing Counsel objects
    immediately (LiveKit's built-in interruption). opposing_counsel.py / judge.py / verification.py
    are used through streaming_verify — this file only connects the audio layer around them.
Depends on: livekit-agents + plugins (see requirements-voice.txt); config, judge,
    streaming_verify, objection_classifier, session_state, voice_interrupt
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
import time

from livekit import agents
from livekit.agents import Agent, AgentSession, WorkerOptions, cli, inference
from livekit.agents.tts import StreamAdapter
from livekit.plugins import deepgram, elevenlabs, openai, silero

import backend_client
import config
import judge
import scorecard_builder
from judge_participant import JudgeParticipant
from judge_voice import JudgeVoice
from objection_classifier import ObjectionClassifier
from session_state import SessionState
from streaming_verify import astream_verified_reply
from voice_interrupt import build_objection_event, handle_interim

logger = logging.getLogger("lexpar.agents")


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
    the verification in verification.py, orchestrated by streaming_verify (§6.5): this overrides
    the LLM step so the pipeline speaks *our* verified sentences — streamed, so TTS starts on
    sentence 1 while sentence 2 is still generating/verifying — instead of a stock completion.
    """

    def __init__(self, state: SessionState, turn_flags: dict):
        super().__init__(instructions="You are opposing counsel in a courtroom rehearsal session.")
        self._state = state
        self._turn_flags = turn_flags  # {"objected": bool} — shared with judge_rule (main.py)

    async def on_user_turn_completed(self, turn_ctx, new_message) -> None:
        # Record ONE coherent attorney turn per completed utterance. Deepgram emits many `is_final`
        # segments within a single spoken turn; committing here (instead of per-segment) is what
        # keeps the saved transcript from shredding into fragments. The classifier still sees every
        # interim via the separate user_input_transcribed handler.
        text = (getattr(new_message, "text_content", "") or "").strip()
        if text:
            self._state.add_turn("attorney", text)

    async def llm_node(self, chat_ctx, tools, model_settings):
        # Courtroom flow: if an objection already fired on this turn, Opposing Counsel already spoke
        # ("Objection — <type>.") and the Judge already ruled — so DON'T also deliver a full
        # end-of-turn argument. It would be redundant, re-object after the ruling, and race the
        # ruling through the TTS queue. Reset the per-turn flag and stay silent; the full reply
        # still runs on turns where no objection fired (normal cross-examination).
        if self._turn_flags.get("objected"):
            self._turn_flags["objected"] = False
            logger.info("objection fired this turn — skipping the full OC reply (object → rule)")
            return
        attorney_turn = _last_user_text(chat_ctx)
        spoken: list[str] = []
        # Blocking generate/verify runs in a worker thread inside the bridge; the event loop stays
        # responsive. On a mid-stream verification failure the pipeline repairs once, else truncates
        # (Option B) — either way every yielded sentence has already passed verification.
        async for sentence in astream_verified_reply(self._state, attorney_turn):
            spoken.append(sentence)
            yield sentence + " "  # trailing space so TTS never jams two sentences together
        if spoken:
            # Accumulate exactly what was spoken (post-verification) for the end-of-session batch.
            self._state.add_turn("opposing_counsel", " ".join(spoken))
        else:
            logger.warning("no verified sentences this turn — staying silent (fail closed)")


async def entrypoint(ctx: agents.JobContext) -> None:
    await ctx.connect()

    session_id = _session_id_from_room(ctx.room)

    # Workers are auto-dispatched into EVERY new room on the server. Only rooms named
    # "session-<uuid>" are real sparring sessions (livekit_token.py); anything else (scratch/test
    # rooms, user-scoped rooms) would just 422 on every backend call — no-op instead of running
    # the whole voice pipeline in a ghost room.
    if not backend_client.is_valid_session_id(session_id):
        logger.warning("room %r is not a session room — agent idle, not starting", ctx.room.name)
        return

    # Load the session's case facts from the backend (agent-authed) so verification + the judge
    # reason with the real case. Non-fatal: if it fails, start with empty facts rather than crash.
    case_facts = ""
    try:
        context = await asyncio.to_thread(backend_client.get_session_context, session_id)
        case_facts = context.get("case_facts", "")
    except Exception:
        logger.warning("could not load case context for %s; starting with empty facts", session_id)

    state = SessionState(case_facts=case_facts)
    classifier = ObjectionClassifier(state)
    # Shared with OpposingCounselAgent.llm_node: set when an objection fires on a turn so the
    # end-of-turn full reply is skipped (object → rule → continue, no redundant re-argument).
    turn_flags = {"objected": False}

    # ElevenLabs' multi-stream-input websocket (the plugin's default `.stream()` path) returns no
    # audio on our free-tier account — replies were never voiced and the socket closed 1006. Wrap
    # the TTS in StreamAdapter, which synthesizes sentence-by-sentence over the HTTP `/stream`
    # endpoint (verified working on this account) instead of the websocket. See docs/LESSONS.md.
    eleven_tts = elevenlabs.TTS(
        model=config.ELEVENLABS_MODEL,
        voice_id=config.ELEVENLABS_VOICE_ID,
        api_key=config.ELEVENLABS_API_KEY,
    )

    # The Judge speaks with a DISTINCT voice (like a real courtroom — tellable apart by ear). One
    # AgentSession has one TTS, so judge lines are synthesized on this second instance and played
    # through session.say(audio=...) rather than the session's own (Opposing Counsel) voice.
    judge_tts = elevenlabs.TTS(
        model=config.ELEVENLABS_MODEL,
        voice_id=config.JUDGE_VOICE_ID,
        api_key=config.ELEVENLABS_API_KEY,
    )

    session = AgentSession(
        # Silero VAD needs no API key. STT/TTS keys are passed EXPLICITLY from our own config
        # (config.py) rather than relying on each plugin's implicit env-var lookup — ElevenLabs
        # otherwise looks for ELEVEN_API_KEY, not our ELEVENLABS_API_KEY (see docs/LESSONS.md).
        vad=silero.VAD.load(),
        # Pin LOCAL inference for both turn handling knobs — the SDK's auto-detect prefers LiveKit
        # Cloud services (dev mode even resolves the turn detector to the cloud "v1"), which we
        # don't have on a self-hosted server:
        #  - interruption "adaptive" → cloud inference: ~5s of connect retries per session.
        #  - turn detection "v1" → cloud detector: a 401 before falling back to the local mini
        #    model. "v1-mini" IS that local model, pinned directly (no cloud transport at all).
        turn_handling={
            "turn_detection": inference.TurnDetector(version="v1-mini"),
            "interruption": {"mode": "vad"},
        },
        stt=deepgram.STT(
            model=config.DEEPGRAM_MODEL,
            interim_results=True,
            api_key=config.DEEPGRAM_API_KEY,
        ),
        # The pipeline requires an llm; OpposingCounselAgent.llm_node overrides how it is used.
        llm=openai.LLM(
            model=config.OPPOSING_COUNSEL_MODEL,
            base_url=config.OPPOSING_COUNSEL_ENDPOINT,
            api_key=config.FIREWORKS_API_KEY,
        ),
        tts=StreamAdapter(tts=eleven_tts),
    )

    async def publish_objection(decision) -> None:
        # Gap 3: emit the structured objection event on the data channel at the barge-in moment so
        # the frontend can render it. reliable=True so it isn't dropped. (livekit-rtc signature —
        # topic/reliable may need tuning against the installed SDK in a live room.)
        event = build_objection_event(decision)
        await ctx.room.local_participant.publish_data(
            json.dumps(event).encode("utf-8"), reliable=True, topic="objection"
        )

    # The Judge is a REAL second room participant (identity "judge", own connection + audio track,
    # judge_participant.py): speaker attribution is correct by construction — the frontend sees the
    # judge participant speaking, no synthetic label events. Judge audio also bypasses the OC
    # session's speech queue, so session.interrupt()/VAD can never cut the judge off.
    judge_participant = JudgeParticipant(
        url=config.LIVEKIT_URL,
        api_key=config.LIVEKIT_API_KEY,
        api_secret=config.LIVEKIT_API_SECRET,
        room_name=ctx.room.name,
        tts=judge_tts,
    )
    judge_connected = await judge_participant.connect()

    async def _publish_judge_speaking(speaking: bool) -> None:
        # FALLBACK-ONLY label signal: when the judge participant is unavailable and the judge is
        # multiplexed onto the OC agent participant, the frontend can't attribute the audio — this
        # brackets it so the UI can still show "Judge speaking".
        try:
            msg = json.dumps({"type": "judge_speaking", "speaking": speaking}).encode("utf-8")
            await ctx.room.local_participant.publish_data(msg, reliable=True, topic="objection")
        except Exception:
            pass

    async def _judge_say_fallback(text: str) -> None:
        # The previous working path (judge voice through the shared agent participant via the
        # session speech queue) — kept verbatim so a judge-participant failure degrades to exactly
        # the old behavior, never to a silent judge.
        async def frames():
            async for synthesized in judge_tts.synthesize(text):
                yield synthesized.frame

        await _publish_judge_speaking(True)
        try:
            handle = session.say(text, audio=frames(), allow_interruptions=False)
            await handle
        finally:
            await _publish_judge_speaking(False)

    judge_voice = JudgeVoice(
        primary=judge_participant.say if judge_connected else None,
        fallback=_judge_say_fallback,
    )

    async def _judge_say(text: str) -> None:
        await judge_voice.say(text)

    async def judge_rule(objection, fragment: str, wait_for_clear) -> None:
        # Inline ruling (§6.5): fast-model call → apply to the ledger IMMEDIATELY → judge speaks
        # "Sustained/Overruled — <reason>" right after OC's objection line. Generation runs
        # concurrently with the canned line's playback, but the SPEAK is gated on `wait_for_clear`
        # (the canned line finishing) — the judge has its own participant/track with no shared
        # speech queue, so without the gate a fast ruling would talk over the objection line.
        # Fail-safe: on any error/timeout the judge stays SILENT and the objection stays PENDING —
        # the end-of-session assessment rules it (never fabricate a penalty). The classifier is on
        # hold() while this runs (voice_interrupt), so no new objection can fire over the judge;
        # the timeout below bounds how long that hold can last if the model call hangs.
        turn_flags["objected"] = True  # skip the redundant end-of-turn OC reply (Issue 1)
        try:
            ruling, reason = await asyncio.wait_for(
                asyncio.to_thread(judge.quick_ruling, state, objection, fragment), timeout=10.0
            )
        except Exception:
            logger.warning("inline ruling unavailable — objection stays pending")
            return
        try:
            state.rule_on_objection(objection, ruling)
        except ValueError:
            return  # already resolved (e.g. session finalized concurrently) — don't speak stale
        spoken = f"{ruling.capitalize()}. {reason}" if reason else f"{ruling.capitalize()}."
        state.add_turn("judge", spoken)
        try:
            await wait_for_clear()  # never speak over the canned objection line
            await _judge_say(spoken)
        except Exception:
            logger.exception("inline ruling could not be spoken (ledger already updated)")
        try:
            # timestamp is a stable id the frontend dedups on (Issue 2) — a redelivered packet
            # can't double-render the judge line.
            event = {
                "type": "ruling",
                "ruling": ruling,
                "reason": reason,
                "timestamp": int(time.time() * 1000),
            }
            await ctx.room.local_participant.publish_data(
                json.dumps(event).encode("utf-8"), reliable=True, topic="objection"
            )
        except Exception:
            pass

    @session.on("user_input_transcribed")
    def _on_user_transcript(event) -> None:
        # Every interim/final fragment feeds the objection classifier; a fire barges in via the
        # tested voice_interrupt glue (debounce + cooldown ensure one objection per utterance,
        # and the ruling hold keeps OC from objecting over the judge). The attorney's *turn* is
        # recorded separately in the agent's on_user_turn_completed hook (one coherent turn),
        # so we do NOT add per-fragment turns here.
        coro = handle_interim(session, classifier, event.transcript, publish_objection, judge_rule)
        asyncio.create_task(coro)

    finalized = {"done": False}

    async def _finalize_session(speak: bool) -> None:
        # End of session, run exactly once: the judge assesses the whole session in one call — rules
        # every pending objection (→ score + weaknesses), extracts the facts the attorney
        # established (→ strengths), gives a closing ruling. If `speak` (the attorney is still in
        # the room, having clicked "End session"), the judge DELIVERS it aloud. Then a batch
        # write persists the transcript + scorecard, and we signal the frontend that it can show the
        # scorecard. Idempotent so the end-session event, participant-disconnect, and shutdown
        # backstops can't double-run the (expensive) judge call.
        if finalized["done"]:
            return
        finalized["done"] = True
        if not any(turn.speaker == "attorney" for turn in state.transcript):
            return
        assessment = await asyncio.to_thread(judge.assess_session, state)
        for objection, ruling in zip(state.pending_objections(), assessment["rulings"]):
            try:
                state.rule_on_objection(objection, ruling)
            except ValueError:
                pass  # unknown/duplicate ruling → leave pending (not sustained, no penalty)
        for fact in assessment["established_facts"]:
            state.add_established_fact(fact)
        ruling = assessment["closing_ruling"]
        state.add_turn("judge", ruling)
        if speak:
            try:
                await _judge_say(ruling)  # the judge delivers it aloud, in the judge's voice
            except Exception:
                logger.exception("judge closing ruling could not be spoken")
        payload = scorecard_builder.build_session_end_payload(state, ruling)
        turn_count = len(state.transcript)
        try:
            await asyncio.to_thread(backend_client.complete_session, session_id)
            await asyncio.to_thread(backend_client.write_scorecard, session_id, payload)
            logger.info("Persisted session %s (scorecard + %d turns)", session_id, turn_count)
        except Exception:
            logger.exception("Failed to persist session %s", session_id)
        # Tell the frontend the ruling is delivered + the scorecard is written, so it can navigate.
        try:
            done = json.dumps({"type": "end_complete"}).encode("utf-8")
            await ctx.room.local_participant.publish_data(done, reliable=True, topic="control")
        except Exception:
            pass

    @ctx.room.on("data_received")
    def _on_data(packet) -> None:
        # The attorney clicked "End session": deliver the judge's spoken ruling + persist, then the
        # frontend waits for our end_complete before navigating to the scorecard.
        if packet.topic != "control":
            return
        try:
            message = json.loads(packet.data.decode("utf-8"))
        except Exception:
            return
        if message.get("type") == "end_session":
            asyncio.create_task(_finalize_session(speak=True))

    @ctx.room.on("participant_disconnected")
    def _on_participant_left(participant) -> None:
        # Backstop: the attorney closed the tab without clicking End — finalize now (no one to hear
        # the ruling) instead of waiting for the room's empty-timeout, so the scorecard still lands.
        asyncio.create_task(_finalize_session(speak=False))

    async def _on_shutdown() -> None:
        await _finalize_session(speak=False)  # last-resort backstop
        await judge_participant.aclose()

    ctx.add_shutdown_callback(_on_shutdown)

    await session.start(agent=OpposingCounselAgent(state, turn_flags), room=ctx.room)


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
