"""
File: agents/llm_metrics.py
Purpose: In-process LLM observability + token accounting (AUDIT_REPORT B7/B8). Every routed LLM
    call records per-role counters (calls, errors, fallback use, latency, prompt/completion
    tokens), and the quality canaries — above all `no_verified_sentences` (OC going silent, the
    failure mode fought live) plus the streaming-verification failure classes — increment named
    counters. `snapshot()` returns it all as a plain dict: main.py logs it at session end and
    ships it in the scorecard payload (`sessions.llm_usage`, migration 0008) as the per-session
    usage record billing will meter from. A Prometheus/OTel exporter is deliberately deferred to
    deploy time — these counters are the source it will read.
Depends on: threading, dataclasses (stdlib only)
Related: agents/llm_router.py (records calls), agents/streaming_verify.py + agents/main.py
    (record canaries), agents/scorecard_builder.py (ships the snapshot), docs/AUDIT_REPORT.md §3
Security notes: Holds and logs COUNTS only — never message content, prompts, or replies.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

logger = logging.getLogger("lexpar.agents.metrics")


@dataclass
class RoleStats:
    """Cumulative counters for one LLM role (opposing_counsel/judge/verification/objection)."""

    calls: int = 0
    errors: int = 0
    fallback_calls: int = 0
    latency_total_s: float = 0.0
    latency_max_s: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0

    def as_dict(self) -> dict:
        return {
            "calls": self.calls,
            "errors": self.errors,
            "fallback_calls": self.fallback_calls,
            "latency_total_s": round(self.latency_total_s, 3),
            "latency_max_s": round(self.latency_max_s, 3),
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
        }


_lock = threading.Lock()
_roles: dict[str, RoleStats] = {}
_canaries: dict[str, int] = {}


def record_call(
    role: str,
    *,
    ok: bool,
    latency_s: float,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    fallback: bool = False,
) -> None:
    """Record one LLM call attempt. Logged at DEBUG (counts only, never content)."""
    key = role or "unknown"
    with _lock:
        stats = _roles.setdefault(key, RoleStats())
        stats.calls += 1
        if not ok:
            stats.errors += 1
        if fallback:
            stats.fallback_calls += 1
        stats.latency_total_s += latency_s
        stats.latency_max_s = max(stats.latency_max_s, latency_s)
        stats.prompt_tokens += prompt_tokens
        stats.completion_tokens += completion_tokens
    logger.debug(
        "llm call role=%s ok=%s fallback=%s latency=%.2fs tokens=%d/%d",
        key, ok, fallback, latency_s, prompt_tokens, completion_tokens,
    )


def record_canary(name: str) -> None:
    """Increment a named quality canary (e.g. no_verified_sentences, sentence_rejected,
    reply_truncated, repair_attempted, stream_error). The rate of these — not any single one —
    is the operate-this-for-customers signal (AUDIT B7)."""
    with _lock:
        _canaries[name] = _canaries.get(name, 0) + 1


def snapshot() -> dict:
    """Everything recorded so far, as a plain JSON-serializable dict."""
    with _lock:
        return {
            "roles": {role: stats.as_dict() for role, stats in _roles.items()},
            "canaries": dict(_canaries),
        }


def reset() -> None:
    """Zero all counters (tests; and main.py at session start so per-process snapshots are
    per-session when the worker runs one job per process — the LiveKit default)."""
    with _lock:
        _roles.clear()
        _canaries.clear()
