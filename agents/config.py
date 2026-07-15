"""
File: agents/config.py
Purpose: Load agent configuration from the environment (repo-root .env) and expose per-role LLM
    provider / endpoint / model settings plus the Fireworks API key. Centralizes env reading so
    llm_router and the agents don't each re-parse os.environ.
Depends on: python-dotenv (stdlib os otherwise)
Related: agents/llm_router.py, .env.example, docs/ARCHITECTURE.md §7 / §9
Security notes: FIREWORKS_API_KEY comes from the environment only — never hardcode it or log it.
    .env is gitignored; .env.example documents the shape.
"""

import os
from pathlib import Path

import certifi
from dotenv import load_dotenv

# Load the repo-root .env (one level above agents/) if present. Real shell/CI env still wins,
# since load_dotenv does not override variables already set in the environment.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Wire a CA bundle for aiohttp-based clients (the LiveKit Deepgram/ElevenLabs/inference plugins).
# macOS python.org builds ship with NO default CA file (ssl cafile=None), so every aiohttp TLS
# connection fails CERTIFICATE_VERIFY_FAILED while httpx-based clients (openai, backend_client)
# work — they bundle certifi themselves. setdefault so an explicitly set SSL_CERT_FILE wins.
# See docs/LESSONS.md ("aiohttp TLS fails on macOS python.org builds").
os.environ.setdefault("SSL_CERT_FILE", certifi.where())

_FIREWORKS_ENDPOINT = "https://api.fireworks.ai/inference/v1"

FIREWORKS_API_KEY = os.getenv("FIREWORKS_API_KEY", "")
# vLLM and other OpenAI-compatible self-hosted servers usually ignore the key; a placeholder is
# enough for the client to construct.
SELF_HOSTED_API_KEY = os.getenv("SELF_HOSTED_API_KEY", "EMPTY")

# Model defaults are the chat models actually deployed on this Fireworks account (llama/gemma are
# not available here). All overridable via env. NOTE: none of the available models is truly
# "small" — the verifier points at a clean JSON-following model distinct from the reasoning model;
# swap VERIFICATION_LLM_MODEL for a smaller/faster one once deployed (ARCHITECTURE §6.5).

# Opposing Counsel — the main reasoning model.
OPPOSING_COUNSEL_PROVIDER = os.getenv("OPPOSING_COUNSEL_LLM_PROVIDER", "fireworks")
OPPOSING_COUNSEL_ENDPOINT = os.getenv("OPPOSING_COUNSEL_LLM_ENDPOINT", _FIREWORKS_ENDPOINT)
OPPOSING_COUNSEL_MODEL = os.getenv(
    "OPPOSING_COUNSEL_LLM_MODEL",
    "accounts/fireworks/models/deepseek-v4-pro",
)

# Judge — should be Gemma for bonus eligibility (§7), but no serverless Gemma is reachable on this
# account (verified: /v1/models has none; Gemma 2/3/4 IDs all 404). INTERIM: gpt-oss-120b, used
# via structured JSON output (judge.py) — fast (~2-3s) and reliable. deepseek-v4-pro was rejected
# for the Judge: as a reasoning model it is slow (30-60s) and intermittently returns empty content.
# Move to a Gemma model via JUDGE_LLM_MODEL once one is deployed.
JUDGE_PROVIDER = os.getenv("JUDGE_LLM_PROVIDER", "fireworks")
JUDGE_ENDPOINT = os.getenv("JUDGE_LLM_ENDPOINT", _FIREWORKS_ENDPOINT)
JUDGE_MODEL = os.getenv("JUDGE_LLM_MODEL", "accounts/fireworks/models/gpt-oss-120b")

# Verification — deliberately NOT the reasoning model (ARCHITECTURE §6.5); a clean JSON follower.
VERIFICATION_PROVIDER = os.getenv("VERIFICATION_LLM_PROVIDER", "fireworks")
VERIFICATION_ENDPOINT = os.getenv("VERIFICATION_LLM_ENDPOINT", _FIREWORKS_ENDPOINT)
VERIFICATION_MODEL = os.getenv(
    "VERIFICATION_LLM_MODEL",
    "accounts/fireworks/models/gpt-oss-120b",
)

# Objection classifier — the most latency-sensitive call (runs on streaming speech). Fast JSON
# follower; gpt-oss-120b for now (benchmarked ~1-2s), swap via env if a faster model appears.
OBJECTION_PROVIDER = os.getenv("OBJECTION_LLM_PROVIDER", "fireworks")
OBJECTION_ENDPOINT = os.getenv("OBJECTION_LLM_ENDPOINT", _FIREWORKS_ENDPOINT)
OBJECTION_MODEL = os.getenv(
    "OBJECTION_LLM_MODEL",
    "accounts/fireworks/models/gpt-oss-120b",
)

# Voice pipeline (agents/main.py). We read the keys from our OWN env names here and pass them
# EXPLICITLY into the plugins (main.py) — do not rely on each plugin's implicit env-var lookup,
# whose names don't all match ours (Deepgram defaults to DEEPGRAM_API_KEY, which matches, but
# ElevenLabs defaults to ELEVEN_API_KEY, which does NOT match our ELEVENLABS_API_KEY convention).
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
DEEPGRAM_MODEL = os.getenv("DEEPGRAM_MODEL", "nova-3")

# How long (seconds) the attorney must keep speaking before it INTERRUPTS the agent mid-utterance.
# The SDK default is 0.5s, which lets a brief noise/echo (a breath, "um", speaker bleed) cut
# Opposing Counsel off before it produces a single audio frame — the confirmed cause of OC being
# inaudible in live sessions (VAD false-interruptions, worse without headphones). Raised to 1.0s so
# only sustained speech interrupts; tune up (1.5-2.0) via INTERRUPTION_MIN_DURATION if OC is still
# getting cut off, or down if genuine interruptions feel unresponsive. (We stay on VAD interruption
# mode — the SDK's "adaptive" mode needs cloud inference we don't have on a self-hosted server; see
# docs/LESSONS.md.)
INTERRUPTION_MIN_DURATION = float(os.getenv("INTERRUPTION_MIN_DURATION", "1.0"))
ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_flash_v2_5")  # low-latency Flash
# Default: "George" — a CURRENT premade voice. The old default ("Rachel", 21m00Tcm4TlvDq8ikWAM)
# is a legacy/library voice: free-tier API calls to it fail 402 "paid_plan_required" at synthesis
# time even with a valid key. Verify a voice with a real synthesis call, not just key validity.
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb")
# The Judge speaks with a DISTINCT voice from Opposing Counsel — a user should tell who's speaking
# by voice alone, like a real courtroom. Default: "Daniel" (premade, free-tier-verified alongside
# George/Sarah).
JUDGE_VOICE_ID = os.getenv("JUDGE_VOICE_ID", "onwK4e9ZLuTAKqWW03F9")


def _getbool(name: str, default: bool) -> bool:
    """Parse a boolean env var (1/true/yes/on = True); default when unset."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


# Use ElevenLabs' native streaming websocket (multi-stream-input) as the AgentSession TTS — the true
# low-latency path (audio starts as the model generates, not after a whole HTTP synthesis per
# sentence). That websocket yields ZERO audio on the FREE tier (opens then closes 1006), which is
# why the TTS was historically wrapped in StreamAdapter over the slower HTTP `/stream` endpoint. On
# a PAID tier the websocket works, so this defaults ON. Set ELEVENLABS_STREAMING=false to fall back
# to the HTTP path — a one-line rollback if the websocket ever misbehaves. See docs/LESSONS.md.
ELEVENLABS_STREAMING = _getbool("ELEVENLABS_STREAMING", True)

# auto_mode on the streaming websocket: generate audio IMMEDIATELY per flushed segment instead of
# buffering ~120+ chars (the plugin's chunk_length_schedule) before the first byte. Our pipeline
# feeds the socket one COMPLETE verified sentence at a time — exactly the feed pattern ElevenLabs
# recommends auto_mode for. Without it, a short first sentence sat buffered for seconds of dead
# air: the attorney talked over the silence, and the interrupt then waited the full 5s
# speech-timeout on audio that never started ("speech not done in time" ×6 in one live session,
# text-without-voice OC lines, and ~5s of hidden stall inside every objection's interrupt+say).
ELEVENLABS_AUTO_MODE = _getbool("ELEVENLABS_AUTO_MODE", True)

# Natural floor-contest dynamics (floor_dynamics.py): when the attorney talks over OC, OC asks for
# the floor and completes its point; on repeated cut-offs the judge intervenes ("order"). Default
# OFF — the live path is byte-identical until FLOOR_DYNAMICS=true is set explicitly, and one env
# line turns it back off (same rollback pattern as ELEVENLABS_STREAMING).
FLOOR_DYNAMICS = _getbool("FLOOR_DYNAMICS", False)

# Derive "the matter before the court" once at room join (case_posture.derive_matter) — the shared
# frame OC and the Judge reason against so OC opposes the attorney's position on a stable, case-
# grounded matter instead of inventing a side on a thin opening. Default ON; one FAST-model call at
# session start, best-effort (a failure just leaves the matter empty). Set DERIVE_MATTER=false to
# roll back to reasoning from the case summary + exchange alone.
DERIVE_MATTER = _getbool("DERIVE_MATTER", True)

# Recover attorney turns the SDK drops (turn_recovery.py): a user turn that completes while
# non-interruptible agent speech is playing is DISCARDED before on_user_turn_completed (verified in
# the installed SDK) — the second casualty of OC non-interruptibility (docs/LESSONS.md). Buffered
# STT finals not covered by the next committed turn are flushed into the record instead of lost.
# Default ON; false restores the previous (lossy) behavior in one env line.
RECOVER_DROPPED_TURNS = _getbool("RECOVER_DROPPED_TURNS", True)

# Case-aware STT vocabulary (stt_keyterms.py): boost THIS case's party names / entities as Deepgram
# nova-3 `keyterm`s so domain terms stop being misheard ("TCT" → "VLT" live). Default ON; false
# runs the STT unboosted exactly as before.
STT_KEYTERMS = _getbool("STT_KEYTERMS", True)

# Cap on how long an interrupted speech may take to wind down before it is hard-cancelled
# (overrides the SDK's INTERRUPTION_TIMEOUT, default 5.0s). Live, an objection's force-interrupt
# of OC's streaming reply waited up to that full wind-down before the canned "Objection!" could
# start — measured interrupt+say up to 5.3s (the wind-down blocks on the in-flight generation
# closing, which can't be hurried). 1.5s keeps normal wind-downs (milliseconds) unaffected and
# bounds the worst case; the hard cancel is safe — llm_node's finally still records what was
# actually spoken. Set <= 0 to leave the SDK default untouched.
INTERRUPT_CANCEL_TIMEOUT_S = float(os.getenv("INTERRUPT_CANCEL_TIMEOUT_S", "1.5"))

# Minimum seconds between objection fires (the classifier's re-fire time floor). The code default
# (5s, DEFAULT_REFIRE_COOLDOWN — kept for offline harnesses/tests) let an objection land on nearly
# EVERY substantive attorney turn live: each one cancels OC's forming counter-argument and skips
# its reply, so OC only ever objected and never argued. 20s gives the courtroom a real rhythm —
# object, ruling, then an arguing window. Tune by ear; lower for a more combative opponent.
OBJECTION_REFIRE_COOLDOWN_S = float(os.getenv("OBJECTION_REFIRE_COOLDOWN_S", "20.0"))


def _getfloat(name: str, default: float) -> float:
    """Parse a float env var; default when unset/invalid (a bad value must not kill the worker)."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


# Turn-taking pacing (the fragmentation fix). Deepgram's plugin default endpointing is 25 ms —
# any mid-sentence breath finalized the turn, so one spoken argument shredded into 3-4 turns and
# OC replied to each fragment (the live "chattiness"). These are the three knobs, all env-tunable
# on the droplet without a rebuild (same pattern as INTERRUPTION_MIN_DURATION):
# - DEEPGRAM_ENDPOINTING_MS: silence (ms) before Deepgram emits a FINAL. Higher = fewer fragments,
#   but finals also gate the argument-proceeding objection fallback, so too high delays objections.
# - MIN/MAX_ENDPOINTING_DELAY: how long the session waits before committing end-of-turn (the
#   semantic turn detector can extend within [min, max]). Raising min lets a brief pause continue
#   the same turn instead of handing OC the floor.
DEEPGRAM_ENDPOINTING_MS = int(_getfloat("DEEPGRAM_ENDPOINTING_MS", 300))
MIN_ENDPOINTING_DELAY = _getfloat("MIN_ENDPOINTING_DELAY", 0.8)
MAX_ENDPOINTING_DELAY = _getfloat("MAX_ENDPOINTING_DELAY", 6.0)


# ElevenLabs voice_settings (expressiveness). These were previously UNSET, so ElevenLabs used each
# voice's flat dashboard defaults — the main cause of monotone delivery. `style` is the primary
# expressiveness dial (0 = flat/old behavior; higher = more expressive but adds inference latency);
# lower `stability` = more emotive but less consistent turn-to-turn. Kept in config so they are
# tuned by ear via .env in a live pass (this feature is fundamentally about how it SOUNDS) — set
# OC_VOICE_STYLE=0 to revert exactly to the old flat delivery. main.py builds the plugin's
# VoiceSettings from these dicts (config.py stays livekit-free for CI).
OC_VOICE_SETTINGS = {
    # OC is on the latency-critical streaming/interruption path — style kept modest, speaker-boost
    # off, so the expressiveness bump doesn't add perceptible lag. Drop OC_VOICE_STYLE if it does.
    "stability": _getfloat("OC_VOICE_STABILITY", 0.40),
    "similarity_boost": _getfloat("OC_VOICE_SIMILARITY_BOOST", 0.75),
    "style": _getfloat("OC_VOICE_STYLE", 0.30),
    "use_speaker_boost": _getbool("OC_VOICE_USE_SPEAKER_BOOST", False),
}
JUDGE_VOICE_SETTINGS = {
    # Judge (quick + final ruling, same fast instance in Track A) — a touch more gravitas/authority
    # (speaker-boost on). quick_ruling is FAST_TIMEOUT-bound; lower JUDGE_VOICE_STYLE if it lags.
    "stability": _getfloat("JUDGE_VOICE_STABILITY", 0.42),
    "similarity_boost": _getfloat("JUDGE_VOICE_SIMILARITY_BOOST", 0.80),
    "style": _getfloat("JUDGE_VOICE_STYLE", 0.38),
    "use_speaker_boost": _getbool("JUDGE_VOICE_USE_SPEAKER_BOOST", True),
}

# Track B (gated): use ElevenLabs v3 + authored audio tags for the Judge's FINAL ruling only, where
# the SessionFinale deliberation-wave gives real latency slack. OFF by default — turn on only after
# the live v3-on-/stream smoke test confirms v3 renders on the plugin's HTTP path and sounds right.
# OC live replies and the Judge's quick_ruling stay on the fast model regardless.
JUDGE_EXPRESSIVE_FINAL_RULING = _getbool("JUDGE_EXPRESSIVE_FINAL_RULING", False)
JUDGE_V3_MODEL = os.getenv("JUDGE_V3_MODEL", "eleven_v3")

# Backend persistence (Gap 4): the worker completes the session + writes the scorecard/transcript
# at session end, authenticating with the scoped agent service token (NOT a user login).
AGENT_BACKEND_URL = os.getenv("AGENT_BACKEND_URL", "http://localhost:8000")
AGENT_SERVICE_TOKEN = os.getenv("AGENT_SERVICE_TOKEN", "")

# LiveKit connection — the agents SDK reads these from env itself; exposed here because the worker
# ALSO mints the judge participant's token locally (judge_participant.py) and needs them directly.
LIVEKIT_URL = os.getenv("LIVEKIT_URL", "ws://localhost:7880")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY", "")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET", "")
