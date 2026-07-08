"""
File: agents/llm_router.py
Purpose: Point each agent at the correct OpenAI-compatible LLM endpoint per ARCHITECTURE §7.
    Reads provider/endpoint/model from config and returns a ready OpenAI client + model id, so
    switching Fireworks ↔ self-hosted vLLM is a config change, not a code fork (both speak the
    OpenAI API). Also provides a thin `chat()` helper used by the agents and the verifier.
Depends on: openai, agents/config.py
Related: agents/opposing_counsel.py, agents/judge.py, agents/verification.py,
    docs/ARCHITECTURE.md §7
Security notes: Reads the provider API key from config (environment only) — never log it.
"""

from __future__ import annotations

from dataclasses import dataclass

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


def _api_key(provider: str) -> str:
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
    """Construct an OpenAI-compatible client for the given routing (no network call here)."""
    client = OpenAI(base_url=cfg.endpoint, api_key=_api_key(cfg.provider))
    return LlmEndpoint(client=client, model=cfg.model)


def chat(
    endpoint: LlmEndpoint,
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.7,
    max_tokens: int = 512,
    response_format: dict | None = None,
) -> str:
    """Run a chat completion and return the message text (empty if the model returns none)."""
    kwargs: dict = {}
    if response_format is not None:
        kwargs["response_format"] = response_format
    response = endpoint.client.chat.completions.create(
        model=endpoint.model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        **kwargs,
    )
    return response.choices[0].message.content or ""
