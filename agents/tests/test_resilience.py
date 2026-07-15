"""
File: agents/tests/test_resilience.py
Purpose: Phase 2 resilience + observability tests (docs/AUDIT_REPORT.md B7/B8): retry with
    backoff, per-role fallback failover, the per-endpoint circuit breaker (open → skip primary →
    half-open recovery), the stream rule (retry ONLY before the first yielded delta), llm_metrics
    counters/canaries, and the scorecard payload carrying the usage snapshot.
Depends on: pytest; agents/llm_router.py, agents/llm_metrics.py, agents/scorecard_builder.py
Related: docs/AUDIT_REPORT.md §3, agents/tests/test_reliability.py (Phase 1)
Security notes: No live API calls — every model call here is a fake.
"""

from __future__ import annotations

import pytest

import llm_metrics
import llm_router
import scorecard_builder
from llm_router import Breaker, LlmEndpoint
from session_state import SessionState

MESSAGES = [{"role": "user", "content": "hi"}]


class _ScriptedCompletions:
    """create() plays through `script`: each entry is an Exception to raise, a string to return
    as content, or a list of strings to stream as deltas."""

    def __init__(self, script: list):
        self.script = list(script)
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        action = self.script.pop(0) if self.script else RuntimeError("script exhausted")
        if isinstance(action, Exception):
            raise action
        from types import SimpleNamespace

        if kwargs.get("stream"):
            deltas = action if isinstance(action, list) else [action]
            out = []
            for d in deltas:
                if isinstance(d, Exception):
                    out.append(d)
                else:
                    out.append(
                        SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=d))])
                    )
            return _RaisingIter(out)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=action))]
        )


class _RaisingIter:
    """Iterates chunks; raises when it meets an Exception entry (mid-stream failure)."""

    def __init__(self, items):
        self._items = iter(items)

    def __iter__(self):
        return self

    def __next__(self):
        item = next(self._items)
        if isinstance(item, Exception):
            raise item
        return item


def _endpoint(script: list, role: str = "test", fallback_script: list | None = None) -> LlmEndpoint:
    from types import SimpleNamespace

    completions = _ScriptedCompletions(script)
    ep = LlmEndpoint(
        client=SimpleNamespace(chat=SimpleNamespace(completions=completions)),
        model="fake",
        role=role,
    )
    ep._completions = completions  # test-side handle
    if fallback_script is not None:
        fb = _endpoint(fallback_script, role=role)
        ep.fallback = fb
    return ep


@pytest.fixture(autouse=True)
def _fast_and_clean(monkeypatch):
    monkeypatch.setattr(llm_router, "_sleep", lambda s: None)  # no real backoff in tests
    llm_metrics.reset()
    yield
    llm_metrics.reset()


# --- retry ------------------------------------------------------------------------------------


def test_chat_retries_then_succeeds():
    ep = _endpoint([RuntimeError("blip"), "recovered"])
    assert llm_router.chat(ep, MESSAGES, retries=1) == "recovered"
    assert ep._completions.calls == 2


def test_chat_retries_zero_fails_fast():
    ep = _endpoint([RuntimeError("down"), "never reached"])
    with pytest.raises(RuntimeError):
        llm_router.chat(ep, MESSAGES, retries=0)
    assert ep._completions.calls == 1


# --- fallback failover ------------------------------------------------------------------------


def test_chat_fails_over_to_fallback():
    ep = _endpoint([RuntimeError("down"), RuntimeError("down")], fallback_script=["from fallback"])
    assert llm_router.chat(ep, MESSAGES, retries=1) == "from fallback"
    assert ep._completions.calls == 2  # primary: 1 + 1 retry
    assert ep.fallback._completions.calls == 1


def test_chat_without_fallback_raises_after_retries():
    ep = _endpoint([RuntimeError("down"), RuntimeError("down")])
    with pytest.raises(RuntimeError):
        llm_router.chat(ep, MESSAGES, retries=1)


def test_metrics_record_fallback_use():
    ep = _endpoint([RuntimeError("down")], fallback_script=["ok"])
    llm_router.chat(ep, MESSAGES, retries=0)
    stats = llm_metrics.snapshot()["roles"]["test"]
    assert stats["calls"] == 2 and stats["errors"] == 1 and stats["fallback_calls"] == 1


# --- circuit breaker --------------------------------------------------------------------------


def test_breaker_opens_after_threshold_and_recovers():
    clock = {"t": 0.0}
    breaker = Breaker(threshold=2, cooldown_s=60.0, clock=lambda: clock["t"])
    assert not breaker.is_open()
    breaker.record_failure()
    assert not breaker.is_open()
    breaker.record_failure()
    assert breaker.is_open()  # threshold hit
    clock["t"] = 61.0
    assert not breaker.is_open()  # cooldown elapsed → half-open
    breaker.record_failure()
    assert breaker.is_open()  # half-open failure re-opens immediately
    breaker.record_success()
    assert not breaker.is_open()  # success closes


def test_open_breaker_skips_primary_entirely():
    ep = _endpoint(["never called"], fallback_script=["from fallback"])
    ep.breaker = Breaker(threshold=1, cooldown_s=600.0)
    ep.breaker.record_failure()  # trip it
    assert llm_router.chat(ep, MESSAGES, retries=0) == "from fallback"
    assert ep._completions.calls == 0  # primary skipped — that's the breaker's point


def test_open_breaker_without_fallback_still_tries_primary():
    ep = _endpoint(["still served"])
    ep.breaker = Breaker(threshold=1, cooldown_s=600.0)
    ep.breaker.record_failure()
    assert llm_router.chat(ep, MESSAGES, retries=0) == "still served"  # never dead-ends


# --- streaming: retry only before the first delta ----------------------------------------------


def test_stream_retries_before_first_delta():
    ep = _endpoint([RuntimeError("connect fail"), ["Hello ", "world."]])
    assert list(llm_router.chat_stream(ep, MESSAGES, retries=1)) == ["Hello ", "world."]
    assert ep._completions.calls == 2


def test_stream_never_restarts_after_first_delta():
    # First attempt yields one delta, THEN dies mid-stream: the error must propagate (the text
    # may already be spoken — a restart would re-speak), not silently restart.
    ep = _endpoint([["Spoken ", RuntimeError("mid-stream")], ["never", "reached"]])
    received = []
    with pytest.raises(RuntimeError):
        for delta in llm_router.chat_stream(ep, MESSAGES, retries=1):
            received.append(delta)
    assert received == ["Spoken "]
    assert ep._completions.calls == 1


def test_stream_fails_over_before_first_delta():
    ep = _endpoint([RuntimeError("down")], fallback_script=[["From ", "fallback."]])
    assert list(llm_router.chat_stream(ep, MESSAGES, retries=0)) == ["From ", "fallback."]


# --- metrics + canaries + payload --------------------------------------------------------------


def test_canaries_count_and_snapshot():
    llm_metrics.record_canary("no_verified_sentences")
    llm_metrics.record_canary("no_verified_sentences")
    llm_metrics.record_canary("reply_truncated")
    snap = llm_metrics.snapshot()
    assert snap["canaries"] == {"no_verified_sentences": 2, "reply_truncated": 1}


def test_tokens_accumulate_per_role():
    from types import SimpleNamespace

    ep = _endpoint(["fine"])
    # graft usage onto the scripted response
    original = ep._completions.create

    def with_usage(**kwargs):
        resp = original(**kwargs)
        resp.usage = SimpleNamespace(prompt_tokens=120, completion_tokens=30)
        return resp

    ep._completions.create = with_usage
    llm_router.chat(ep, MESSAGES, retries=0)
    stats = llm_metrics.snapshot()["roles"]["test"]
    assert stats["prompt_tokens"] == 120 and stats["completion_tokens"] == 30


def test_session_end_payload_carries_llm_usage():
    usage = {"roles": {"judge": {"calls": 2}}, "canaries": {}}
    payload = scorecard_builder.build_session_end_payload(SessionState(), "r", llm_usage=usage)
    assert payload["llm_usage"] == usage
    # And omitting it stays additive (older callers): empty dict, never a KeyError.
    assert scorecard_builder.build_session_end_payload(SessionState(), "r")["llm_usage"] == {}
