"""
File: app/rate_limit.py
Purpose: Minimal in-memory sliding-window rate limiter for the UNAUTHENTICATED auth routes
    (login/register) — without it the admin password handed to demo judges is open to unlimited
    brute force. In-memory is deliberate: the stack runs ONE backend container (docker-compose),
    so no shared store is needed; if the backend ever scales horizontally, replace with a
    Redis-backed limiter (noted in tasks/PLAN.md Tier 2).
Depends on: fastapi (Request), stdlib
Related: app/api/auth.py (the two gated routes), infra/Caddyfile (the proxy that sets XFF)
Security notes: The client key comes from X-Forwarded-For when present — trustworthy HERE because
    the backend port is not public; only Caddy (which sets XFF from the real peer) can reach it.
    On a direct/dev deployment the socket peer address is used. Never log the attempted bodies.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

# 10 attempts per rolling minute per client — generous for a human retyping a password,
# useless for a brute force.
AUTH_LIMIT = 10
AUTH_WINDOW_S = 60.0


class SlidingWindowLimiter:
    """Per-key sliding window. Thread-safe (uvicorn may serve requests on a threadpool)."""

    def __init__(self, limit: int, window_s: float, clock=time.monotonic) -> None:
        self._limit = limit
        self._window_s = window_s
        self._clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = self._clock()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > self._window_s:
                hits.popleft()
            if len(hits) >= self._limit:
                return False
            hits.append(now)
            return True

    def reset(self) -> None:
        """Testing hook — clears all windows (autouse fixture keeps tests isolated)."""
        with self._lock:
            self._hits.clear()


auth_limiter = SlidingWindowLimiter(AUTH_LIMIT, AUTH_WINDOW_S)


def _client_key(request: Request) -> str:
    # Behind Caddy every socket peer is Caddy itself — the real client is the FIRST entry of
    # X-Forwarded-For (Caddy appends the true peer; the port is not publicly reachable, so the
    # header can't be spoofed past it). Direct/dev connections fall back to the socket peer.
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def auth_rate_limit(request: Request) -> None:
    """FastAPI dependency for the unauthenticated auth routes."""
    if not auth_limiter.allow(_client_key(request)):
        raise HTTPException(
            status_code=429, detail="Too many attempts. Wait a minute and try again."
        )
