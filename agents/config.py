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

from dotenv import load_dotenv

# Load the repo-root .env (one level above agents/) if present. Real shell/CI env still wins,
# since load_dotenv does not override variables already set in the environment.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

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

# Voice pipeline (agents/main.py). The Deepgram/ElevenLabs plugins read their API keys from the
# environment (DEEPGRAM_API_KEY / ELEVENLABS_API_KEY); these just pick the models/voice.
DEEPGRAM_MODEL = os.getenv("DEEPGRAM_MODEL", "nova-3")
ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_flash_v2_5")  # low-latency Flash
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
