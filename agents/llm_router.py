"""
File: agents/llm_router.py
Purpose: Point each agent at the correct OpenAI-compatible LLM endpoint per ARCHITECTURE §7.
    Reads provider/endpoint/model from config and returns a ready OpenAI client + model id, so
    switching Fireworks ↔ self-hosted vLLM is a config change, not a code fork (both speak the
    OpenAI API). Provides a thin `chat()` helper (blocking, full completion) used by the agents and
    the verifier, and `chat_stream()` (yields text deltas) used by the streaming sentence-level
    verification path (ARCHITECTURE §6.5).
Depends on: openai, agents/config.py
Related: agents/opposing_counsel.py, agents/judge.py, agents/verification.py,
    docs/ARCHITECTURE.md §7
Security notes: Reads the provider API key from config (environment only) — never log it.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache

from openai import OpenAI

import config


@dataclass(frozen=True)
class LlmConfig:
    """Resolved routing for one role: which provider, endpoint, and model."""

    provider: str
    endpoint: str
    model: str


@dataclass
class LlmEndpoint:
    """A constructed client bound to a specific model."""

    client: OpenAI
    model: str


def api_key_for(provider: str) -> str:
    """The API key for a provider: the Fireworks key for `fireworks`, else the self-hosted key.
    Public so callers that build their own OpenAI-compatible client (e.g. the LiveKit voice
    pipeline's base LLM) resolve the key the same way — keeping the Fireworks↔vLLM switch a pure
    config change (ARCHITECTURE §10.5)."""
    if provider == "fireworks":
        return config.FIREWORKS_API_KEY or "EMPTY"
    return config.SELF_HOSTED_API_KEY


def opposing_counsel_config() -> LlmConfig:
    return LlmConfig(
        config.OPPOSING_COUNSEL_PROVIDER,
        config.OPPOSING_COUNSEL_ENDPOINT,
        config.OPPOSING_COUNSEL_MODEL,
    )


def judge_config() -> LlmConfig:
    return LlmConfig(config.JUDGE_PROVIDER, config.JUDGE_ENDPOINT, config.JUDGE_MODEL)


def verification_config() -> LlmConfig:
    return LlmConfig(
        config.VERIFICATION_PROVIDER,
        config.VERIFICATION_ENDPOINT,
        config.VERIFICATION_MODEL,
    )


def objection_config() -> LlmConfig:
    return LlmConfig(
        config.OBJECTION_PROVIDER,
        config.OBJECTION_ENDPOINT,
        config.OBJECTION_MODEL,
    )


def build_endpoint(cfg: LlmConfig) -> LlmEndpoint:
    """Construct a FRESH OpenAI-compatible client for the given routing (no network call here).
    Prefer `pooled_endpoint` on the live paths — a fresh client per call re-does connection setup
    and defeats httpx connection pooling (AUDIT B1)."""
    client = OpenAI(base_url=cfg.endpoint, api_key=api_key_for(cfg.provider))
    return LlmEndpoint(client=client, model=cfg.model)


@lru_cache(maxsize=None)
def pooled_endpoint(cfg: LlmConfig) -> LlmEndpoint:
    """The shared, connection-pooled client for a routing config. One client per distinct
    LlmConfig for the process lifetime (the OpenAI client is thread-safe; a config change lands
    on the next deploy/restart, like the prompt cache). Every live call site uses this."""
    return build_endpoint(cfg)


def _resolve_timeout(timeout: float | None) -> float:
    """The per-call timeout: the caller's explicit value, else the global default. Without an
    explicit ceiling the OpenAI SDK waits 600s — one hung provider connection pinned a pooled
    worker thread for 10 minutes and degraded every concurrent session (AUDIT B4)."""
    return timeout if timeout is not None else config.LLM_TIMEOUT_S


def chat(
    endpoint: LlmEndpoint,
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.7,
    max_tokens: int = 512,
    response_format: dict | None = None,
    timeout: float | None = None,
) -> str:
    """Run a chat completion and return the message text (empty if the model returns none).
    Always time-bounded (`timeout`, default config.LLM_TIMEOUT_S) — callers fail closed/safe."""
    kwargs: dict = {}
    if response_format is not None:
        kwargs["response_format"] = response_format
    response = endpoint.client.chat.completions.create(
        model=endpoint.model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=_resolve_timeout(timeout),
        **kwargs,
    )
    return response.choices[0].message.content or ""


def chat_stream(
    endpoint: LlmEndpoint,
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.7,
    max_tokens: int = 512,
    timeout: float | None = None,
) -> Iterator[str]:
    """Run a streaming chat completion, yielding text deltas as they arrive (§6.5 streaming).
    `timeout` (default config.LLM_TIMEOUT_S) is the httpx read timeout — it bounds the wait
    BETWEEN chunks, so a mid-stream stall raises instead of hanging the producer thread."""
    stream = endpoint.client.chat.completions.create(
        model=endpoint.model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
        timeout=_resolve_timeout(timeout),
    )
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta is not None and delta.content:
            yield delta.content
