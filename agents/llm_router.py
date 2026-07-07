"""
File: agents/llm_router.py
Purpose: Points each agent at the correct OpenAI-compatible LLM endpoint. Eventually reads
    OPPOSING_COUNSEL_LLM_PROVIDER / JUDGE_LLM_PROVIDER (and their endpoints) and returns the
    right client, so switching Fireworks ↔ self-hosted vLLM is a config change, not a code fork.
Depends on: environment config (ARCHITECTURE §9), an OpenAI-compatible client
Related: docs/ARCHITECTURE.md §7 (routing table), agents/opposing_counsel.py, agents/judge.py
Security notes: Reads provider API keys from the environment only — never hardcode or log them.
"""

# TODO: implement once Fireworks/Deepgram/ElevenLabs keys are available
