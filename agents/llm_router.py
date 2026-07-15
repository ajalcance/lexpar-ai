"""
File: agents/llm_router.py
Purpose: Point each agent at the correct OpenAI-compatible LLM endpoint per ARCHITECTURE §7.
    Reads provider/endpoint/model from config and returns a ready OpenAI client + model id, so
    switching Fireworks ↔ self-hosted vLLM is a config change, not a code fork (both speak the
    OpenAI API). Provides a thin `chat()` helper (blocking, full completion) used by the agents and
    the verifier, and `chat_stream()` (yields text deltas) used by the streaming sentence-level
    verification path (ARCHITECTURE §6.5).

    Phase 2 resilience (AUDIT_REPORT B8) — every routed call now carries, in one place:
    - a TIMEOUT (Phase 1): default config.LLM_TIMEOUT_S; stream = read-timeout between chunks;
    - RETRY with backoff: config.LLM_RETRIES extra attempts (callers on hard latency budgets pass
      retries=0); a stream retries ONLY before its first yielded delta — after text has been
      spoken a restart would re-speak, so mid-stream errors propagate (fail-closed downstream);
    - per-role FALLBACK routing: `*_LLM_FALLBACK_{PROVIDER,ENDPOINT,MODEL}` — when the primary
      exhausts its attempts, the same call runs against the fallback endpoint (unset = none);
    - a CIRCUIT BREAKER per endpoint: after LLM_CB_FAILURES consecutive failures the primary is
      skipped for LLM_CB_COOLDOWN_S and calls go straight to the fallback — a dead provider stops
      costing timeout+retry on every call. One success closes the circuit. Never dead-ends: with
      no fallback configured the primary is always still tried.
    - METRICS: every attempt records into llm_metrics (role, ok, latency, tokens, fallback flag).
Depends on: openai, agents/config.py, agents/llm_metrics.py
Related: agents/opposing_counsel.py, agents/judge.py, agents/verification.py,
    docs/ARCHITECTURE.md §7, docs/AUDIT_REPORT.md §3
Security notes: Reads the provider API key from config (environment only) — never log it.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from functools import lru_cache

from openai import OpenAI

import config
import llm_metrics

# Injectable for tests (retry backoff must not slow the suite).
_sleep = time.sleep


@dataclass(frozen=True)
class LlmConfig:
    """Resolved routing for one role: which provider, endpoint, and model. `role` labels metrics
    and selects the fallback routing; "" (offline harness/test configs) means neither applies."""

    provider: str
    endpoint: str
    model: str
    role: str = ""


class Breaker:
    """Per-endpoint circuit breaker (thread-safe). Opens after `threshold` CONSECUTIVE failures;
    while open (within `cooldown_s`), `is_open()` is True and callers skip the endpoint when they
    have somewhere else to go. After the cooldown one attempt flows again (half-open): a success
    closes the circuit, a failure re-opens it immediately. threshold <= 0 disables."""

    def __init__(
        self,
        threshold: int | None = None,
        cooldown_s: float | None = None,
        clock=time.monotonic,
    ):
        self._threshold = config.LLM_CB_FAILURES if threshold is None else threshold
        self._cooldown_s = config.LLM_CB_COOLDOWN_S if cooldown_s is None else cooldown_s
        self._clock = clock
        self._lock = threading.Lock()
        self._consecutive_failures = 0
        self._opened_at: float | None = None

    def is_open(self) -> bool:
        with self._lock:
            if self._opened_at is None:
                return False
            if self._clock() - self._opened_at >= self._cooldown_s:
                return False  # cooldown elapsed — half-open: let one attempt through
            return True

    def record_success(self) -> None:
        with self._lock:
            self._consecutive_failures = 0
            self._opened_at = None

    def record_failure(self) -> None:
        with self._lock:
            self._consecutive_failures += 1
            if 0 < self._threshold <= self._consecutive_failures:
                self._opened_at = self._clock()


@dataclass
class LlmEndpoint:
    """A constructed client bound to a specific model, with its resilience state. `fallback` is
    the alternate endpoint calls fail over to (None = single-provider, the old behavior)."""

    client: OpenAI
    model: str
    role: str = ""
    fallback: "LlmEndpoint | None" = None
    breaker: Breaker = field(default_factory=Breaker)


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
        role="opposing_counsel",
    )


def judge_config() -> LlmConfig:
    return LlmConfig(
        config.JUDGE_PROVIDER, config.JUDGE_ENDPOINT, config.JUDGE_MODEL, role="judge"
    )


def verification_config() -> LlmConfig:
    return LlmConfig(
        config.VERIFICATION_PROVIDER,
        config.VERIFICATION_ENDPOINT,
        config.VERIFICATION_MODEL,
        role="verification",
    )


def objection_config() -> LlmConfig:
    return LlmConfig(
        config.OBJECTION_PROVIDER,
        config.OBJECTION_ENDPOINT,
        config.OBJECTION_MODEL,
        role="objection",
    )


def fallback_config(role: str) -> LlmConfig | None:
    """The role's fallback routing from config (`*_LLM_FALLBACK_*`), or None when unset. Read at
    call time (not import) so tests can monkeypatch config."""
    triples = {
        "opposing_counsel": config.OPPOSING_COUNSEL_FALLBACK,
        "judge": config.JUDGE_FALLBACK,
        "verification": config.VERIFICATION_FALLBACK,
        "objection": config.OBJECTION_FALLBACK,
    }
    triple = triples.get(role)
    if triple is None:
        return None
    provider, endpoint, model = triple
    return LlmConfig(provider, endpoint, model, role=role)


def build_endpoint(cfg: LlmConfig) -> LlmEndpoint:
    """Construct a FRESH OpenAI-compatible client for the given routing (no network call here).
    Prefer `pooled_endpoint` on the live paths — a fresh client per call re-does connection setup
    and defeats httpx connection pooling (AUDIT B1)."""
    client = OpenAI(base_url=cfg.endpoint, api_key=api_key_for(cfg.provider))
    return LlmEndpoint(client=client, model=cfg.model, role=cfg.role)


@lru_cache(maxsize=None)
def pooled_endpoint(cfg: LlmConfig) -> LlmEndpoint:
    """The shared, connection-pooled client for a routing config — one client (and one breaker)
    per distinct LlmConfig for the process lifetime (the OpenAI client is thread-safe; a config
    change lands on the next deploy/restart, like the prompt cache). The role's configured
    fallback endpoint is attached here, once, so every call site gets failover for free."""
    endpoint = build_endpoint(cfg)
    fb_cfg = fallback_config(cfg.role)
    if fb_cfg is not None and fb_cfg != cfg:  # a fallback identical to the primary is pointless
        endpoint.fallback = build_endpoint(fb_cfg)
    return endpoint


def _resolve_timeout(timeout: float | None) -> float:
    """The per-call timeout: the caller's explicit value, else the global default. Without an
    explicit ceiling the OpenAI SDK waits 600s — one hung provider connection pinned a pooled
    worker thread for 10 minutes and degraded every concurrent session (AUDIT B4)."""
    return timeout if timeout is not None else config.LLM_TIMEOUT_S


def _resolve_retries(retries: int | None) -> int:
    return retries if retries is not None else config.LLM_RETRIES


def _usage_tokens(response) -> tuple[int, int]:
    """(prompt_tokens, completion_tokens) from a completion, 0s when the server omits usage."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return 0, 0
    return (getattr(usage, "prompt_tokens", 0) or 0, getattr(usage, "completion_tokens", 0) or 0)


def _attempt_plan(endpoint: LlmEndpoint) -> list[tuple[LlmEndpoint, bool]]:
    """The endpoints to try, in order, as (endpoint, is_fallback). An OPEN primary breaker skips
    straight to the fallback (that's the breaker's whole point); with no fallback configured the
    primary is always tried — the breaker never dead-ends a call."""
    if endpoint.fallback is None:
        return [(endpoint, False)]
    if endpoint.breaker.is_open():
        return [(endpoint.fallback, True)]
    return [(endpoint, False), (endpoint.fallback, True)]


def chat(
    endpoint: LlmEndpoint,
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.7,
    max_tokens: int = 512,
    response_format: dict | None = None,
    timeout: float | None = None,
    retries: int | None = None,
) -> str:
    """Run a chat completion and return the message text (empty if the model returns none).
    Time-bounded, retried, failed over, and metered — see the module docstring. `retries` is per
    endpoint (primary and fallback each get 1 + retries attempts); pass 0 on hard latency paths."""
    kwargs: dict = {}
    if response_format is not None:
        kwargs["response_format"] = response_format
    attempts = _resolve_retries(retries)
    last_error: Exception | None = None
    for candidate, is_fallback in _attempt_plan(endpoint):
        for attempt in range(attempts + 1):
            started = time.perf_counter()
            try:
                response = candidate.client.chat.completions.create(
                    model=candidate.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=_resolve_timeout(timeout),
                    **kwargs,
                )
                prompt_tokens, completion_tokens = _usage_tokens(response)
                llm_metrics.record_call(
                    candidate.role,
                    ok=True,
                    latency_s=time.perf_counter() - started,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    fallback=is_fallback,
                )
                candidate.breaker.record_success()
                return response.choices[0].message.content or ""
            except Exception as error:
                llm_metrics.record_call(
                    candidate.role,
                    ok=False,
                    latency_s=time.perf_counter() - started,
                    fallback=is_fallback,
                )
                candidate.breaker.record_failure()
                last_error = error
                if attempt < attempts:
                    _sleep(config.LLM_RETRY_BACKOFF_S)
    raise last_error  # type: ignore[misc]  # the plan always has >= 1 attempt


def chat_stream(
    endpoint: LlmEndpoint,
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.7,
    max_tokens: int = 512,
    timeout: float | None = None,
    retries: int | None = None,
) -> Iterator[str]:
    """Run a streaming chat completion, yielding text deltas as they arrive (§6.5 streaming).
    `timeout` is the httpx read timeout — it bounds the wait BETWEEN chunks. Retry/failover apply
    ONLY before the first delta is yielded: once text is out it may already be spoken, so a
    restart would re-speak — mid-stream errors propagate and the caller fails closed
    (streaming_verify truncates at the last verified sentence)."""
    attempts = _resolve_retries(retries)
    last_error: Exception | None = None
    for candidate, is_fallback in _attempt_plan(endpoint):
        for attempt in range(attempts + 1):
            started = time.perf_counter()
            yielded_any = False
            try:
                stream = candidate.client.chat.completions.create(
                    model=candidate.model,
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
                        yielded_any = True
                        yield delta.content
                llm_metrics.record_call(
                    candidate.role,
                    ok=True,
                    latency_s=time.perf_counter() - started,
                    fallback=is_fallback,
                )
                candidate.breaker.record_success()
                return
            except Exception as error:
                llm_metrics.record_call(
                    candidate.role,
                    ok=False,
                    latency_s=time.perf_counter() - started,
                    fallback=is_fallback,
                )
                candidate.breaker.record_failure()
                if yielded_any:
                    raise  # text is already out (possibly spoken) — never restart mid-stream
                last_error = error
                if attempt < attempts:
                    _sleep(config.LLM_RETRY_BACKOFF_S)
    raise last_error  # type: ignore[misc]
