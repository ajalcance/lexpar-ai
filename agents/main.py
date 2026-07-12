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
from datetime import datetime, timezone

from livekit import agents
from livekit.agents import Agent, AgentSession, WorkerOptions, cli, inference
from livekit.agents.tts import StreamAdapter
from livekit.plugins import deepgram, elevenlabs, openai, silero

import backend_client
import config
import floor_dynamics
import judge
import llm_router
import opposing_counsel
import prompts
import scorecard_builder
from judge_participant import JUDGE_IDENTITY, JudgeParticipant
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


# Settle window before OC commits to a reply. An objection fires on the same event-loop tick the
# attorney's turn completes, so the objection→judge_rule task (which sets `objected` and clears the
# speaking floor) can lose the race to this reply. Yielding briefly, then re-checking, lets the
# objection path win deterministically — so a just-fired objection reliably suppresses the reply
# instead of OC talking over the ruling on the judge's own track. OC replies are not latency-
# critical (the objection + ruling are), so a sub-second settle is invisible.
_OC_REPLY_SETTLE_S = 0.4

# Grace window after the attorney's participant disconnects before the session is finalized. A
# browser refresh or a transient network drop reconnects well inside this; without it, one blip
# force-completed the session (status != in_progress), killing the frontend's "Resume session".
ATTORNEY_DISCONNECT_GRACE_S = 15.0


class OpposingCounselAgent(Agent):
    """
    Opposing Counsel routed into LiveKit. The persona + generation live in opposing_counsel.py and
    the verification in verification.py, orchestrated by streaming_verify (§6.5): this overrides
    the LLM step so the pipeline speaks *our* verified sentences — streamed, so TTS starts on
    sentence 1 while sentence 2 is still generating/verifying — instead of a stock completion.
    """

    def __init__(
        self,
        state: SessionState,
        turn_flags: dict,
        turn_timing: dict,
        session_id: str = "",
        judge_idle=None,
        floor=None,
        speak_judge_order=None,
    ):
        super().__init__(instructions="You are opposing counsel in a courtroom rehearsal session.")
        self._state = state
        self._turn_flags = turn_flags  # {"objected": bool} — shared with judge_rule (main.py)
        # {"attorney_started_at": datetime|None} — set on the user_state→speaking signal in
        # entrypoint so the committed attorney turn is timestamped at its START, not turn-end.
        self._turn_timing = turn_timing
        self._session_id = session_id  # for per-turn pleading retrieval (§12)
        # Speaking floor: the judge (its own participant/track) and OC (the session track) are
        # independent audio outputs with no shared queue, so without this they can talk over each
        # other — a ruling and OC's reply to the NEXT rapid STT-final collided live. This Event is
        # SET when the judge is idle; llm_node awaits it before speaking so OC never starts a reply
        # while the bench is ruling. The judge always has the floor (it's the court).
        self._judge_idle = judge_idle
        # Floor dynamics (flag-gated, floor_dynamics.py): FloorTracker instance or None, plus the
        # injected judge-order speaker (async () -> None, holds the judge floor internally).
        self._floor = floor
        self._speak_judge_order = speak_judge_order

    async def on_user_turn_completed(self, turn_ctx, new_message) -> None:
        # Record ONE coherent attorney turn per completed utterance. Deepgram emits many `is_final`
        # segments within a single spoken turn; committing here (instead of per-segment) is what
        # keeps the saved transcript from shredding into fragments. The classifier still sees every
        # interim via the separate user_input_transcribed handler.
        text = (getattr(new_message, "text_content", "") or "").strip()
        # Timestamp the turn at the moment the attorney STARTED speaking, not now (turn-end).
        # Objections/rulings fire mid-utterance (on an interim) and are recorded then; if the
        # attorney turn were timestamped at turn-end it would sort AFTER them, so the report would
        # show the objection before the statement it objects to. Start-time keeps order. CONSUME it
        # (set None) so a brief mid-sentence pause→resume can't leave a stale start for the next
        # turn; the observer re-arms on the next fresh utterance (None → turn-end fallback is safe).
        started = self._turn_timing.get("attorney_started_at")
        self._turn_timing["attorney_started_at"] = None
        if text:
            self._state.add_turn("attorney", text, spoken_at=started)
            if self._floor is not None:
                # Floor dynamics: the speech that cut OC off became a REAL committed turn — this
                # is the corroboration that promotes a cut-off candidate to a retry (an echo/VAD
                # blip never reaches here, so it can never trigger the courtesy dance).
                self._floor.attorney_turn_committed()

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
        # Settle-and-recheck: close the race where an objection fires on the same tick the turn
        # completes and this reply beats judge_rule to setting `objected` / clearing the floor.
        await asyncio.sleep(_OC_REPLY_SETTLE_S)
        if self._turn_flags.get("objected"):
            self._turn_flags["objected"] = False
            logger.info("objection fired this turn (post-settle) — skipping the full OC reply")
            return
        # Wait for the bench to finish before OC takes the floor — the judge speaks on its own
        # track with no shared speech queue, so this is the only thing preventing OC's reply from
        # overlapping a ruling (e.g. a ruling on one STT-final vs. OC's reply to the next).
        if self._judge_idle is not None:
            await self._judge_idle.wait()
        attorney_turn = _last_user_text(chat_ctx)
        spoken: list[str] = []
        # Floor dynamics (flag-gated): if the attorney cut OC off last turn (corroborated), OC gets
        # ONE retry — it asks for the floor and completes the interrupted point. On a streak of
        # cut-offs the JUDGE intervenes instead ("order"), so OC needn't ask — the bench just gave
        # it the floor. The cutoff note carries the interrupted point into the prompt (OC's
        # messages are rebuilt fresh each turn, so without it the retry would be amnesiac).
        cutoff_note = ""
        retry = self._floor.take_retry() if self._floor is not None else None
        if retry is not None:
            partial, original_turn = retry
            cutoff_note = floor_dynamics.cutoff_note(partial, original_turn)
            if self._floor.should_judge_intervene() and self._speak_judge_order is not None:
                logger.info("floor dynamics: judge order intervention")
                await self._speak_judge_order()
            else:
                logger.info("floor dynamics: OC floor request")
                spoken.append(floor_dynamics.OC_FLOOR_REQUEST)
                yield floor_dynamics.OC_FLOOR_REQUEST + " "
        # Ground the reply in the pleading: retrieve the passages relevant to this turn (§12) via
        # the session-bound generator. Blocking generate/verify runs in a worker thread inside the
        # bridge; the event loop stays responsive. On a mid-stream verification failure the pipeline
        # repairs once, else truncates (Option B) — every yielded sentence has passed verification.
        session_id = self._session_id

        def _generate(state, turn):
            return opposing_counsel.stream_reply(state, turn, session_id, cutoff_note)

        completed = False
        try:
            async for sentence in astream_verified_reply(
                self._state, attorney_turn, generate=_generate
            ):
                # Re-check the floor PER SENTENCE, not just at reply start. A reply that already
                # passed the opening gate can be paused by the attorney speaking and later resumed
                # (the SDK's pause/resume on a sub-threshold interruption); if a ruling started in
                # between, feeding more text would speak over the judge. Gating each sentence bounds
                # any overlap to the audio already buffered, and if an objection fired on the
                # attorney speech that caused the pause, session.interrupt() cancels this generator
                # outright (the `finally` still records what was actually voiced).
                if self._judge_idle is not None:
                    await self._judge_idle.wait()
                spoken.append(sentence)
                yield sentence + " "  # trailing space so TTS never jams two sentences together
            completed = True
        finally:
            # In a `finally` so the reply is recorded EVEN IF it's interrupted mid-stream — VAD /
            # session.interrupt() closes this async generator, and without this a cut-off OC reply
            # would leave NO trace in the transcript (the reason OC looked absent from the record).
            # `spoken` holds exactly the verified sentences that were actually voiced.
            if spoken:
                reply = " ".join(spoken)
                self._state.add_turn("opposing_counsel", reply)
                # Invariant guard (observability only): OC's spoken reply is counter-argument and
                # must NOT lodge an objection — the word "objection" may only come from the
                # structured barge-in, which the judge rules. If OC slips, the transcript would show
                # an unruled "objection", so surface it in the logs (never rewrite the reply).
                low = reply.lower()
                lodged = ("i object" in low or "objection, your honor" in low
                          or "objection your honor" in low)
                if lodged:
                    logger.warning(
                        "OC reply lodged an objection in counter-argument (unruled) — tighten "
                        "oc_reply_style/opposing_counsel prompt if this recurs"
                    )
            else:
                logger.warning("no verified sentences this turn — staying silent (fail closed)")
            if self._floor is not None:
                # Floor dynamics: a reply that ended naturally resets the contest; one whose
                # generator was closed early (VAD / session.interrupt()) is a cut-off CANDIDATE,
                # carrying the partial already voiced + the turn it answered (the retry's memory).
                # Promotion waits for the interrupting speech to become a real attorney turn.
                if completed:
                    self._floor.reply_completed()
                else:
                    logger.info("floor dynamics: cut-off candidate recorded")
                    self._floor.reply_cut_off(" ".join(spoken), attorney_turn)


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
    # Shared with OpposingCounselAgent.on_user_turn_completed: the wall-clock instant the attorney
    # began the current utterance, captured from the user_state→speaking signal below, so the
    # committed attorney turn is ordered by speech START (keeps mid-utterance objections/rulings
    # after the statement they respond to — see the transcript-ordering fix).
    turn_timing: dict = {"attorney_started_at": None}
    # Speaking floor between the judge (own track) and OC (session track): SET = judge idle. The
    # judge clears it while ruling; OC's llm_node awaits it, so the two never talk over each other.
    judge_idle = asyncio.Event()
    judge_idle.set()
    # Floor dynamics (flag-gated): the cut-off → floor-request → judge-order state machine.
    floor = floor_dynamics.FloorTracker() if config.FLOOR_DYNAMICS else None

    # ElevenLabs' multi-stream-input websocket (the plugin's `.stream()` path) yields no audio on a
    # FREE-tier account (socket opens then closes 1006) — the historical reason we wrapped the TTS
    # in StreamAdapter over the slower HTTP `/stream` endpoint. On a PAID tier the websocket works,
    # so the transport is now a config switch (config.ELEVENLABS_STREAMING, applied below at
    # `session_tts`) — default streaming, one-line env rollback to the HTTP path. See LESSONS.md.
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

    # Session TTS transport: on a PAID tier use ElevenLabs' native streaming websocket directly
    # (audio as the model generates — the low-latency path). StreamAdapter (HTTP `/stream`, one
    # whole synthesis per sentence) stays as the reversible fallback for the free tier / if the
    # websocket ever misbehaves — flip ELEVENLABS_STREAMING=false to switch, no code change.
    session_tts = eleven_tts if config.ELEVENLABS_STREAMING else StreamAdapter(tts=eleven_tts)
    logger.info(
        "session TTS transport: %s",
        "native streaming websocket" if config.ELEVENLABS_STREAMING else "StreamAdapter (HTTP)",
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
        tts=session_tts,
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
    if judge_connected:
        # Publish the judge track + a silent priming frame immediately, so the browser subscribes
        # and autoplay-unlocks it during the join window. Otherwise the FIRST ruling publishes a
        # brand-new track and its audio is lost before the browser finishes subscribing — the
        # objection #1 "no audible ruling" race (judge_participant.prime / docs/LESSONS.md).
        await judge_participant.prime()

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

    async def speak_judge_order() -> None:
        # Floor dynamics: the bench polices repeated cut-offs. Recorded as a judge turn (so the
        # saved transcript reads like the room sounded) but it never touches the objection ledger,
        # so rulings/scorecard are unaffected. Holds the judge floor like every other bench line.
        judge_idle.clear()
        try:
            state.add_turn("judge", floor_dynamics.JUDGE_ORDER_LINE)
            await _judge_say(floor_dynamics.JUDGE_ORDER_LINE)
        except Exception:
            logger.exception("judge order line could not be spoken")
        finally:
            judge_idle.set()

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
        if floor is not None:
            floor.objection_fired()  # objection supersedes the floor-request courtesy dance
        # Take the speaking floor from the moment the objection fires until the ruling is fully
        # spoken, so OC can't reply to a subsequent STT-final while the bench is still ruling. Held
        # across generation + speech; the finally ALWAYS releases it (timeout, error, or success).
        judge_idle.clear()
        try:
            await _judge_rule_impl(objection, fragment, wait_for_clear)
        finally:
            judge_idle.set()

    async def _judge_rule_impl(objection, fragment: str, wait_for_clear) -> None:
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

    # A false interruption (a brief noise/echo read as the attorney speaking) is the signal that the
    # VAD interruption threshold is too low for the room — if these recur, raise
    # config.INTERRUPTION_MIN_DURATION (see docs/LESSONS.md). Kept as a lightweight ops warning.
    @session.on("agent_false_interruption")
    def _on_false_interruption(ev) -> None:
        logger.warning(
            "agent speech was falsely interrupted (resumed=%s) — if frequent, raise "
            "INTERRUPTION_MIN_DURATION",
            ev.resumed,
        )
        if floor is not None:
            floor.false_interruption()  # the SDK says it was noise — veto the cut-off candidate

    @session.on("user_state_changed")
    def _track_attorney_turn_start(ev) -> None:
        # Record when the attorney FIRST starts a fresh utterance so the turn committed in
        # on_user_turn_completed is timestamped at its START (transcript-ordering fix). Set only
        # when unset — a brief mid-sentence pause flips speaking→listening→speaking, and overwriting
        # on each resume would stamp the turn at the LAST resume, re-introducing the mis-order.
        # on_user_turn_completed consumes (clears) it, re-arming this for the next utterance.
        if ev.new_state == "speaking" and turn_timing["attorney_started_at"] is None:
            turn_timing["attorney_started_at"] = datetime.now(timezone.utc)

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
            # Hold the speaking floor for the closing ruling too, so a still-streaming OC reply
            # can't overlap the bench's final word. Released in the finally.
            judge_idle.clear()
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
            finally:
                judge_idle.set()
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

    async def _finalize_after_grace() -> None:
        # Wait out the grace window, then finalize ONLY if no attorney came back — a refresh
        # rejoins within seconds and the session must keep running for "Resume session" to work.
        await asyncio.sleep(ATTORNEY_DISCONNECT_GRACE_S)
        attorney_present = any(
            p.identity != JUDGE_IDENTITY for p in ctx.room.remote_participants.values()
        )
        if attorney_present:
            logger.info("attorney rejoined within the grace period — session continues")
            return
        await _finalize_session(speak=False)

    @ctx.room.on("participant_disconnected")
    def _on_participant_left(participant) -> None:
        # Backstop: the attorney left without clicking End — finalize (no one to hear the ruling)
        # so the scorecard still lands. IDENTITY-CHECKED: the judge participant is our own second
        # connection (§6.5); a transient blip on it must never end the session. The attorney gets
        # a grace window to rejoin before finalization (idempotent either way).
        if getattr(participant, "identity", "") == JUDGE_IDENTITY:
            logger.warning("judge participant disconnected — session continues")
            return
        asyncio.create_task(_finalize_after_grace())

    async def _on_shutdown() -> None:
        await _finalize_session(speak=False)  # last-resort backstop
        await judge_participant.aclose()

    ctx.add_shutdown_callback(_on_shutdown)

    await session.start(
        agent=OpposingCounselAgent(
            state, turn_flags, turn_timing, session_id, judge_idle, floor, speak_judge_order
        ),
        room=ctx.room
    )


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
