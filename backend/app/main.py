"""
File: app/main.py
Purpose: FastAPI application entrypoint — configures logging, registers routers, exposes an
    unauthenticated /health check, and attaches a request-id correlation middleware (audit
    trail groundwork per DEV_GUIDELINES §8).
Depends on: fastapi, app/api/*
Related: docs/ARCHITECTURE.md §5, alembic (owns schema creation — this app does not create tables)
Security notes: The middleware logs method/path/status + a request id only — never request or
    response bodies, which can carry case facts or transcripts.
"""

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, cases, internal, livekit_token, scorecards, sessions
from app.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("lexpar")

app = FastAPI(title="LexPar AI API", version="0.1.0")

# Allow the browser frontend (Vite dev server) to call the API. Bearer tokens travel in the
# Authorization header, not cookies, so credentials are not needed.
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """Tag each request with a correlation id and log a content-free access line."""
    request_id = str(uuid.uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "%s %s -> %s [req_id=%s]",
        request.method,
        request.url.path,
        response.status_code,
        request_id,
    )
    return response


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Liveness probe — no auth, no DB access."""
    return {"status": "ok"}


for module in (auth, cases, sessions, scorecards, livekit_token, internal):
    app.include_router(module.router)
