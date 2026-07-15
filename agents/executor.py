"""
File: agents/executor.py
Purpose: The worker's DEDICATED, BOUNDED executor for blocking LLM/HTTP work (AUDIT_REPORT B3/B4).
    `asyncio.to_thread` / `run_in_executor(None, …)` share the process-wide default pool
    (min(32, cpu+4) threads, unbounded queue per session): under N concurrent sessions the
    streaming producers + per-sentence verifier calls + rulings all contend head-of-line, and one
    hung provider call (before Phase 1's timeouts) pinned a shared thread for minutes. This module
    gives that work its own pool with an explicit, env-tunable size so blocking LLM work is
    isolated from the SDK's own default-pool usage and its ceiling is a deliberate number.
    Rollback: AGENT_EXECUTOR_WORKERS <= 0 restores the default-pool behavior (run_blocking then
    delegates to the default executor — byte-identical to the old asyncio.to_thread path).
Depends on: asyncio, concurrent.futures (stdlib); agents/config.py
Related: agents/main.py, agents/voice_interrupt.py, agents/streaming_verify.py,
    docs/AUDIT_REPORT.md §3 B3/B4
Security notes: Executes closures that carry transcript/reply text (work product) in memory only —
    nothing here logs arguments or results.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import partial

import config

_executor: ThreadPoolExecutor | None = None


def get_executor() -> ThreadPoolExecutor | None:
    """The shared bounded pool (lazily created), or None when the flag rolls back to the default
    asyncio pool (AGENT_EXECUTOR_WORKERS <= 0). Process-lifetime, like the prompt cache."""
    global _executor
    if config.AGENT_EXECUTOR_WORKERS <= 0:
        return None
    if _executor is None:
        _executor = ThreadPoolExecutor(
            max_workers=config.AGENT_EXECUTOR_WORKERS, thread_name_prefix="lexpar-llm"
        )
    return _executor


async def run_blocking(fn, /, *args, **kwargs):
    """Run blocking `fn` on the bounded pool (or the default pool under rollback) — the drop-in
    replacement for `asyncio.to_thread` on the worker's LLM/HTTP paths."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(get_executor(), partial(fn, *args, **kwargs))
