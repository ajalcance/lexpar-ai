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
ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_flash_v2_5")  # low-latency Flash
# Default: "George" — a CURRENT premade voice. The old default ("Rachel", 21m00Tcm4TlvDq8ikWAM)
# is a legacy/library voice: free-tier API calls to it fail 402 "paid_plan_required" at synthesis
# time even with a valid key. Verify a voice with a real synthesis call, not just key validity.
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb")
# The Judge speaks with a DISTINCT voice from Opposing Counsel — a user should tell who's speaking
# by voice alone, like a real courtroom. Default: "Daniel" (premade, free-tier-verified alongside
# George/Sarah).
JUDGE_VOICE_ID = os.getenv("JUDGE_VOICE_ID", "onwK4e9ZLuTAKqWW03F9")


def _getfloat(name: str, default: float) -> float:
    """Parse a float env var, falling back to the default on missing/malformed input."""
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _getbool(name: str, default: bool) -> bool:
    """Parse a boolean env var (1/true/yes/on = True); default when unset."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


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
