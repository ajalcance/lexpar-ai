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
Depends on: livekit-agents + plugins (see requirements-voice.txt); config, judge, llm_router,
    streaming_verify, objection_classifier, session_state, voice_interrupt, backend_client,
    scorecard_builder, judge_participant (JudgeParticipant), judge_voice (JudgeVoice)
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
import llm_router
import opposing_counsel
import prompts
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

    def __init__(self, state: SessionState, turn_flags: dict, session_id: str = ""):
        super().__init__(instructions="You are opposing counsel in a courtroom rehearsal session.")
        self._state = state
        self._turn_flags = turn_flags  # {"objected": bool} — shared with judge_rule (main.py)
        self._session_id = session_id  # for per-turn pleading retrieval (§12)

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
            # [oc-audio-diag] no reply audio is expected on an objected turn — mark it so a silent
            # OC turn in the logs isn't misread as the bug.
            logger.info("[oc-audio] reply SKIPPED this turn (objection fired) — no OC TTS expected")
            return
        attorney_turn = _last_user_text(chat_ctx)
        spoken: list[str] = []
        # Ground the reply in the pleading: retrieve the passages relevant to this turn (§12) via
        # the session-bound generator. Blocking generate/verify runs in a worker thread inside the
        # bridge; the event loop stays responsive. On a mid-stream verification failure the pipeline
        # repairs once, else truncates (Option B) — every yielded sentence has passed verification.
        session_id = self._session_id

        def _generate(state, turn):
            return opposing_counsel.stream_reply(state, turn, session_id)

        # [oc-audio-diag] TEMPORARY: mark the reply lifecycle so one live run shows whether a reply
        # was generated and text was actually handed to TTS — distinguishing "no reply produced"
        # from "reply produced but never voiced". Remove after the silent-OC diagnosis.
        reply_t0 = time.monotonic()
        logger.info("[oc-audio] reply turn START — generating verified sentences")
        async for sentence in astream_verified_reply(
            self._state, attorney_turn, generate=_generate
        ):
            if not spoken:
                logger.info(
                    "[oc-audio] first verified sentence -> TTS at +%.3fs",
                    time.monotonic() - reply_t0,
                )
            spoken.append(sentence)
            yield sentence + " "  # trailing space so TTS never jams two sentences together
        if spoken:
            logger.info(
                "[oc-audio] reply DONE: %d verified sentence(s) handed to TTS", len(spoken)
            )
            # Accumulate exactly what was spoken (post-verification) for the end-of-session batch.
            self._state.add_turn("opposing_counsel", " ".join(spoken))
        else:
            logger.warning("no verified sentences this turn — staying silent (fail closed)")

    async def tts_node(self, text, model_settings):
        # [oc-audio-diag] TEMPORARY diagnostic — NO behavior change. Delegates to the default
        # tts_node unchanged (same frames, same order, same timing) and only observes the sequence
        # so one live run can tell apart:
        #   (a) TTS never called for the reply  -> no "TTS node ENTER" line for a reply turn
        #   (b) TTS started then interrupted    -> "ENTER" (+ maybe "first frame") then "CANCELLED"
        #   (c) TTS fully synthesized           -> "ENTER" -> "first frame" -> "COMPLETE"
        # Only OC's session-TTS path passes through here; the Judge (own participant) does not.
        # Remove once the failure mode is confirmed from the logs.
        t0 = time.monotonic()
        frames = 0
        logger.info("[oc-audio] TTS node ENTER (synthesizing OC audio)")
        try:
            async for frame in Agent.default.tts_node(self, text, model_settings):
                frames += 1
                if frames == 1:
                    logger.info(
                        "[oc-audio] first TTS audio frame at +%.3fs", time.monotonic() - t0
                    )
                yield frame
            logger.info(
                "[oc-audio] TTS node COMPLETE: %d frame(s) over %.3fs (full synthesis)",
                frames,
                time.monotonic() - t0,
            )
        except (asyncio.CancelledError, GeneratorExit):
            logger.info(
                "[oc-audio] TTS node CANCELLED after %d frame(s) at +%.3fs "
                "(interrupted/cancelled before completion — likely a VAD interruption)",
                frames,
                time.monotonic() - t0,
            )
            raise


async def entrypoint(ctx: agents.JobContext) -> None:
    await ctx.connect()

    # Preload every prompt file once, up front, so no live-path LLM call does file I/O mid-session
    # (prompts.py — the single prompt registry). Cheap; the reads are cached for the process.
    prompts.warm_cache()

    session_id = _session_id_from_room(ctx.room)

    # Load the case context from the backend (agent-authed) so verification + the judge reason with
    # the real case: the raw facts AND the structured pleading summary (§12), which goes into every
    # prompt via SessionState.snapshot(), plus the §13 grounding plumbing (court_id enables
    # court-rules retrieval; proceeding_type gates eligible objection grounds, Phase 4).
    # Non-fatal: if it fails, start empty rather than crash.
    case_facts = ""
    case_summary = ""
    court_id = ""
    proceeding_type = ""
    try:
        context = await asyncio.to_thread(backend_client.get_session_context, session_id)
        case_facts = context.get("case_facts", "")
        case_summary = context.get("case_summary", "")
        court_id = context.get("court_id", "")
        proceeding_type = context.get("proceeding_type", "")
    except Exception:
        logger.warning("could not load case context for %s; starting with empty facts", session_id)

    state = SessionState(
        case_facts=case_facts,
        case_summary=case_summary,
        session_id=session_id,
        court_id=court_id,
        proceeding_type=proceeding_type,
    )
    classifier = ObjectionClassifier(state)
    # Shared with OpposingCounselAgent.llm_node: set when an objection fires on a turn so the
    # end-of-turn full reply is skipped (object → rule → continue, no redundant re-argument).
    turn_flags = {"objected": False}

    # ElevenLabs' multi-stream-input websocket (the plugin's default `.stream()` path) returns no
    # audio on our free-tier account — replies were never voiced and the socket closed 1006. Wrap
    # the TTS in StreamAdapter, which synthesizes sentence-by-sentence over the HTTP `/stream`
    # endpoint (verified working on this account) instead of the websocket. See docs/LESSONS.md.
    # voice_settings drive expressiveness (Track A) — previously UNSET, so ElevenLabs used flat
    # per-voice defaults (the monotone cause). Values come from config (tune by ear via .env).
    eleven_tts = elevenlabs.TTS(
        model=config.ELEVENLABS_MODEL,
        voice_id=config.ELEVENLABS_VOICE_ID,
        voice_settings=elevenlabs.VoiceSettings(**config.OC_VOICE_SETTINGS),
        api_key=config.ELEVENLABS_API_KEY,
    )

    # The Judge speaks with a DISTINCT voice (like a real courtroom — tellable apart by ear). One
    # AgentSession has one TTS, so judge lines are synthesized on this second instance and played
    # through session.say(audio=...) rather than the session's own (Opposing Counsel) voice.
    judge_tts = elevenlabs.TTS(
        model=config.ELEVENLABS_MODEL,
        voice_id=config.JUDGE_VOICE_ID,
        voice_settings=elevenlabs.VoiceSettings(**config.JUDGE_VOICE_SETTINGS),
        api_key=config.ELEVENLABS_API_KEY,
    )

    # Track B (gated): a SECOND judge TTS on ElevenLabs v3 for the FINAL ruling only, where the
    # SessionFinale deliberation-wave gives latency slack. Same voice + settings, v3 model — so the
    # audio tags the expressive assessment prompt authors are rendered. Off unless the env flag is
    # set (after the live v3-on-/stream smoke test). Inline rulings + OC stay on the fast model.
    judge_v3_tts = None
    if config.JUDGE_EXPRESSIVE_FINAL_RULING:
        judge_v3_tts = elevenlabs.TTS(
            model=config.JUDGE_V3_MODEL,
            voice_id=config.JUDGE_VOICE_ID,
            voice_settings=elevenlabs.VoiceSettings(**config.JUDGE_VOICE_SETTINGS),
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
            # min_duration raises the interruption threshold above the SDK default (0.5s) so a
            # brief noise/echo can't cut Opposing Counsel off before it speaks — the confirmed
            # cause of OC being inaudible live (see config.INTERRUPTION_MIN_DURATION + LESSONS.md).
            "interruption": {
                "mode": "vad",
                "min_duration": config.INTERRUPTION_MIN_DURATION,
            },
        },
        stt=deepgram.STT(
            model=config.DEEPGRAM_MODEL,
            interim_results=True,
            api_key=config.DEEPGRAM_API_KEY,
        ),
        # The pipeline requires an llm; OpposingCounselAgent.llm_node overrides how it is used, so
        # this base client isn't actually driven today. Resolve its key the SAME way llm_router does
        # (api_key_for the provider) rather than hardcoding the Fireworks key — so a self_hosted
        # cutover (§10.5) stays a pure config switch for this object too, not a code change.
        llm=openai.LLM(
            model=config.OPPOSING_COUNSEL_MODEL,
            base_url=config.OPPOSING_COUNSEL_ENDPOINT,
            api_key=llm_router.api_key_for(config.OPPOSING_COUNSEL_PROVIDER),
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
        expressive_tts=judge_v3_tts,
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
            result = await asyncio.wait_for(
                asyncio.to_thread(judge.quick_ruling, state, objection, fragment), timeout=10.0
            )
        except Exception:
            logger.warning("inline ruling unavailable — objection stays pending")
            return
        ruling, reason = result.ruling, result.reason
        try:
            state.rule_on_objection(objection, ruling)
        except ValueError:
            return  # already resolved (e.g. session finalized concurrently) — don't speak stale
        # §13 Phase 5: persist the ruling's audit trail (chunks actually shown + turn-scoped
        # citation flags) as soon as the ruling is on the ledger. Fire-and-forget off the loop —
        # provenance must never delay or block the spoken ruling; a failure is logged, not raised.
        async def _persist_provenance() -> None:
            try:
                await asyncio.to_thread(
                    backend_client.write_provenance,
                    session_id,
                    "objection_ruling",
                    result.chunk_ids,
                    result.flagged_citations,
                )
            except Exception:
                logger.warning("could not persist objection-ruling provenance for %s", session_id)

        asyncio.create_task(_persist_provenance())
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
        # so we do NOT add per-fragment turns here. `is_final` enables the comparative-grounds
        # fallback (Option A) for completed finals only — interims stay cheap at the regex gate.
        coro = handle_interim(
            session,
            classifier,
            event.transcript,
            publish_objection,
            judge_rule,
            is_final=event.is_final,
        )
        asyncio.create_task(coro)

    # [oc-audio-diag] TEMPORARY: pure log-only observers of the session's interruption / VAD / state
    # signals so one live run shows WHAT cuts OC's audio. The smoking gun for the leading hypothesis
    # is `agent_false_interruption` (a brief noise/echo was read as speech) and/or `user_state ->
    # speaking` firing WHILE `agent_state == speaking` (OC's own audio leaking into the mic → VAD).
    # No behavior change — these handlers only log. Remove after the diagnosis.
    @session.on("agent_state_changed")
    def _diag_agent_state(ev) -> None:
        logger.info("[oc-audio] agent_state %s -> %s", ev.old_state, ev.new_state)

    @session.on("user_state_changed")
    def _diag_user_state(ev) -> None:
        logger.info("[oc-audio] user_state %s -> %s (VAD)", ev.old_state, ev.new_state)

    @session.on("agent_false_interruption")
    def _diag_false_interruption(ev) -> None:
        logger.info(
            "[oc-audio] agent_false_interruption (resumed=%s) — a brief noise/echo was read as the "
            "attorney speaking and interrupted the agent mid-turn",
            ev.resumed,
        )

    @session.on("speech_created")
    def _diag_speech_created(ev) -> None:
        logger.info(
            "[oc-audio] speech_created source=%s user_initiated=%s", ev.source, ev.user_initiated
        )

    @session.on("error")
    def _diag_error(ev) -> None:
        logger.warning("[oc-audio] session error from %s: %r", type(ev.source).__name__, ev.error)

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
        assessment = await asyncio.to_thread(
            judge.assess_session, state, expressive=config.JUDGE_EXPRESSIVE_FINAL_RULING
        )
        for objection, ruling in zip(state.pending_objections(), assessment["rulings"]):
            try:
                state.rule_on_objection(objection, ruling)
            except ValueError:
                pass  # unknown/duplicate ruling → leave pending (not sustained, no penalty)
        for fact in assessment["established_facts"]:
            state.add_established_fact(fact)
        ruling = assessment["closing_ruling"]  # CLEAN — persisted, displayed, citation-checked
        state.add_turn("judge", ruling)
        if speak:
            try:
                # Track B: the v3 participant speaks the tagged text; a degraded fallback speaks the
                # clean text (never literal tags on flash). When the flag is off, spoken == clean.
                await judge_voice.say(
                    ruling,
                    expressive=config.JUDGE_EXPRESSIVE_FINAL_RULING,
                    expressive_text=assessment["closing_ruling_spoken"],
                )
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
        # §13 Phase 5: the final ruling's audit trail (best-effort — never blocks finalization).
        try:
            await asyncio.to_thread(
                backend_client.write_provenance,
                session_id,
                "final_ruling",
                assessment.get("chunk_ids", []),
                assessment.get("flagged_citations", []),
            )
        except Exception:
            logger.warning("could not persist final-ruling provenance for %s", session_id)
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

    await session.start(
        agent=OpposingCounselAgent(state, turn_flags, session_id), room=ctx.room
    )


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
