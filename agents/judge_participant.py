"""
File: agents/judge_participant.py
Purpose: The Judge as a REAL LiveKit room participant (ARCHITECTURE §6.5) — its own connection,
    identity ("judge"), and audio track — so speaker attribution is correct by construction: the
    frontend knows who is talking from which participant's track is playing, not from a synthetic
    data-channel event. The worker mints the judge's access token locally (livekit-api AccessToken
    is a pure JWT signer, no server call) with publish-only grants, joins the same room over a
    second rtc.Room connection, and speaks by pushing the judge-voice TTS frames into a published
    AudioSource. Judge audio bypasses the Opposing-Counsel AgentSession speech queue entirely, so
    session.interrupt()/VAD can never cut the judge off — non-interruptibility by construction.
Depends on: livekit (rtc), livekit-api; the judge ElevenLabs TTS instance (main.py)
Related: agents/judge_voice.py (fallback wrapper), agents/main.py (wires it),
    docs/ARCHITECTURE.md §6.5, tasks/PLAN.md (design doc)
Security notes: Mints a room-scoped, publish-only token from LIVEKIT_API_KEY/SECRET — never log the
    token. Speaks only judge ruling text (no transcript content beyond what the judge says aloud).

⚠️ Not imported by the CI test suite (livekit is a voice-only dep, requirements-voice.txt). The
livekit-free fallback/selection logic lives in judge_voice.py and IS unit-tested.
"""

from __future__ import annotations

import asyncio
import logging

from livekit import api, rtc

logger = logging.getLogger("lexpar.agents.judge")

JUDGE_IDENTITY = "judge"
JUDGE_NAME = "Judge"
_TOKEN_TTL_S = 6 * 3600  # outlive any realistic session


def build_judge_token(api_key: str, api_secret: str, room_name: str) -> str:
    """Mint a publish-only room token for the judge participant (local JWT, no server call)."""
    return (
        api.AccessToken(api_key, api_secret)
        .with_identity(JUDGE_IDENTITY)
        .with_name(JUDGE_NAME)
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=False,  # the judge only speaks; least privilege
            )
        )
        .to_jwt()
    )


class JudgeParticipant:
    """A second, independent room participant that speaks with the judge's voice."""

    def __init__(self, url: str, api_key: str, api_secret: str, room_name: str, tts) -> None:
        self._url = url
        self._api_key = api_key
        self._api_secret = api_secret
        self._room_name = room_name
        self._tts = tts
        self._room: rtc.Room | None = None
        self._source: rtc.AudioSource | None = None
        self._say_lock = asyncio.Lock()  # judge lines never overlap each other

    async def connect(self) -> bool:
        """Join the room as the judge. Returns False (and logs) on any failure — the caller falls
        back to the session-multiplexed path, so a LiveKit refusal never silences the judge."""
        try:
            token = build_judge_token(self._api_key, self._api_secret, self._room_name)
            room = rtc.Room()
            await room.connect(self._url, token)
            self._room = room
            logger.info("judge participant connected to %s", self._room_name)
            return True
        except Exception:
            logger.exception("judge participant could not connect — falling back to session voice")
            self._room = None
            return False

    async def _ensure_track(self, sample_rate: int, num_channels: int) -> rtc.AudioSource:
        """Publish the judge audio track lazily, sized from the first synthesized frame."""
        if self._source is not None:
            return self._source
        assert self._room is not None
        source = rtc.AudioSource(sample_rate, num_channels)
        track = rtc.LocalAudioTrack.create_audio_track("judge-voice", source)
        options = rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
        await self._room.local_participant.publish_track(track, options)
        self._source = source
        return source

    async def say(self, text: str) -> None:
        """Synthesize `text` on the judge TTS and play it through the judge participant's track.
        Blocks until playout completes (callers sequence rulings after the objection line)."""
        if self._room is None:
            raise RuntimeError("judge participant is not connected")
        async with self._say_lock:
            source: rtc.AudioSource | None = None
            async for synthesized in self._tts.synthesize(text):
                frame = synthesized.frame
                if source is None:
                    source = await self._ensure_track(frame.sample_rate, frame.num_channels)
                await source.capture_frame(frame)
            if source is not None:
                await source.wait_for_playout()

    async def aclose(self) -> None:
        if self._room is not None:
            try:
                await self._room.disconnect()
            except Exception:
                logger.exception("judge participant disconnect failed")
            self._room = None
            self._source = None
