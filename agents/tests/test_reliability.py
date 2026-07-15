"""
File: agents/tests/test_reliability.py
Purpose: Phase 1 reliability-core tests (docs/AUDIT_REPORT.md B3/B4/B9): every LLM call carries a
    timeout (default from config, explicit override wins), clients are pooled per routing config,
    the dedicated executor is bounded + rollback-able, the classifier's debounce holds under REAL
    parallel threads (no double-fire), and the verifier's backpressure gate caps concurrent calls.
Depends on: pytest; agents/llm_router.py, agents/executor.py, agents/objection_classifier.py,
    agents/verification.py, agents/config.py
Related: docs/AUDIT_REPORT.md §3
Security notes: No live API calls — every model call here is a fake.
"""

from __future__ import annotations

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import config
import executor
import llm_router
import verification
from llm_router import LlmConfig, LlmEndpoint
from objection_classifier import DEBOUNCED, FIRE, Decision, ObjectionClassifier
from session_state import SessionState

# --- fakes ------------------------------------------------------------------------------------


class _FakeCompletions:
    """Records the kwargs of the last create() call; returns a canned completion (or chunks)."""

    def __init__(self, stream_chunks: list[str] | None = None):
        self.kwargs: dict | None = None
        self._chunks = stream_chunks

    def create(self, **kwargs):
        self.kwargs = kwargs
        if kwargs.get("stream"):
            return [
                SimpleNamespace(
                    choices=[SimpleNamespace(delta=SimpleNamespace(content=c))]
                )
                for c in (self._chunks or [])
            ]
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
        )


def _fake_endpoint(chunks: list[str] | None = None) -> tuple[LlmEndpoint, _FakeCompletions]:
    completions = _FakeCompletions(chunks)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return LlmEndpoint(client=client, model="fake-model"), completions


# --- timeouts on every LLM call (B4) ----------------------------------------------------------


def test_chat_applies_the_default_timeout():
    endpoint, completions = _fake_endpoint()
    llm_router.chat(endpoint, [{"role": "user", "content": "hi"}])
    assert completions.kwargs["timeout"] == config.LLM_TIMEOUT_S


def test_chat_explicit_timeout_wins():
    endpoint, completions = _fake_endpoint()
    llm_router.chat(endpoint, [{"role": "user", "content": "hi"}], timeout=5.0)
    assert completions.kwargs["timeout"] == 5.0


def test_chat_stream_applies_the_default_timeout():
    endpoint, completions = _fake_endpoint(chunks=["a", "b"])
    out = list(llm_router.chat_stream(endpoint, [{"role": "user", "content": "hi"}]))
    assert out == ["a", "b"]
    assert completions.kwargs["timeout"] == config.LLM_TIMEOUT_S
    assert completions.kwargs["stream"] is True


# --- pooled clients (B1) ----------------------------------------------------------------------


def test_pooled_endpoint_reuses_one_client_per_config():
    cfg = LlmConfig("fireworks", "http://pool-test.invalid/v1", "m1")
    other = LlmConfig("fireworks", "http://pool-test.invalid/v1", "m2")
    assert llm_router.pooled_endpoint(cfg) is llm_router.pooled_endpoint(cfg)
    assert llm_router.pooled_endpoint(cfg) is not llm_router.pooled_endpoint(other)


def test_build_endpoint_stays_fresh_per_call():
    cfg = LlmConfig("fireworks", "http://pool-test.invalid/v1", "m1")
    assert llm_router.build_endpoint(cfg) is not llm_router.build_endpoint(cfg)


# --- bounded executor + rollback (B3) ---------------------------------------------------------


def test_executor_is_bounded_to_the_configured_size(monkeypatch):
    monkeypatch.setattr(executor, "_executor", None)
    monkeypatch.setattr(config, "AGENT_EXECUTOR_WORKERS", 3)
    pool = executor.get_executor()
    assert pool is not None and pool._max_workers == 3


def test_executor_rolls_back_to_the_default_pool(monkeypatch):
    monkeypatch.setattr(executor, "_executor", None)
    monkeypatch.setattr(config, "AGENT_EXECUTOR_WORKERS", 0)
    assert executor.get_executor() is None  # None → asyncio's default pool (old behavior)


def test_run_blocking_executes_and_returns(monkeypatch):
    monkeypatch.setattr(executor, "_executor", None)
    monkeypatch.setattr(config, "AGENT_EXECUTOR_WORKERS", 2)
    assert asyncio.run(executor.run_blocking(lambda a, b: a + b, 40, 2)) == 42


# --- classifier debounce under REAL parallel threads (B9) --------------------------------------


def test_parallel_consider_fires_exactly_once():
    """Eight threads race the same utterance through consider(); the lock + debounce must let
    exactly ONE fire through — a double-fire here would mean two spoken objections live."""
    state = SessionState()

    def always_fire(fragment, st, *, is_final=False):
        time.sleep(0.02)  # widen the race window — a missing lock double-fires reliably here
        return Decision(True, "leading", "test", outcome=FIRE)

    classifier = ObjectionClassifier(state, decider=always_fire)
    fragment = "isn't it true that you signed the agreement"
    with ThreadPoolExecutor(max_workers=8) as pool:
        decisions = list(pool.map(lambda _: classifier.consider(fragment), range(8)))

    assert sum(1 for d in decisions if d.fire) == 1
    assert sum(1 for d in decisions if d.outcome == DEBOUNCED) == 7


# --- verifier backpressure gate (B3) ----------------------------------------------------------


def test_verify_gate_caps_concurrent_calls(monkeypatch):
    """With the gate at 2, six parallel check_consistency calls never overlap more than 2 deep."""
    active = 0
    peak = 0
    lock = threading.Lock()

    def slow_chat(*args, **kwargs):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.05)
        with lock:
            active -= 1
        return '{"consistent": true, "contradictions": []}'

    monkeypatch.setattr(verification, "chat", slow_chat)
    monkeypatch.setattr(verification, "_VERIFY_GATE", threading.BoundedSemaphore(2))

    state = SessionState(case_facts="The contract was signed in March.")
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda _: verification.check_consistency("Fine.", state), range(6)))

    assert all(r == [] for r in results)
    assert peak <= 2


def test_verify_gate_disabled_runs_ungated(monkeypatch):
    monkeypatch.setattr(verification, "chat", lambda *a, **k: '{"contradictions": []}')
    monkeypatch.setattr(verification, "_VERIFY_GATE", None)
    assert verification.check_consistency("Fine.", SessionState()) == []
