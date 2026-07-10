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

# Backend persistence (Gap 4): the worker completes the session + writes the scorecard/transcript
# at session end, authenticating with the scoped agent service token (NOT a user login).
AGENT_BACKEND_URL = os.getenv("AGENT_BACKEND_URL", "http://localhost:8000")
AGENT_SERVICE_TOKEN = os.getenv("AGENT_SERVICE_TOKEN", "")

# LiveKit connection — the agents SDK reads these from env itself; exposed here because the worker
# ALSO mints the judge participant's token locally (judge_participant.py) and needs them directly.
LIVEKIT_URL = os.getenv("LIVEKIT_URL", "ws://localhost:7880")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY", "")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET", "")
