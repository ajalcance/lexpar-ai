"""
File: app/config.py
Purpose: Central application settings loaded from environment variables (.env) per
    ARCHITECTURE §9. Exposes one typed Settings object the rest of the app imports.
Depends on: pydantic-settings
Related: .env.example (documents the shape), docs/ARCHITECTURE.md §9
Security notes: Secrets (JWT_SECRET, provider keys) come from the environment only — never
    hardcode real values here and never log them.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Minimum JWT signing-key length. HS256 keys should be >= 256 bits (RFC 7518 §3.2); this also
# rejects the old insecure default and any blank/short secret.
MIN_JWT_SECRET_LEN = 32

# The project-root .env, resolved from this file's location (backend/app/config.py) rather than a
# path relative to the current working directory. This makes `.env` load reliably whether uvicorn is
# launched from the repo root or from inside backend/ (see docs/LESSONS.md).
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    """Typed view over the environment. Field names map case-insensitively to env vars."""

    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    # Database
    database_url: str = "postgresql://postgres:postgres@localhost:5432/lexpar"

    # Object storage (S3-compatible: MinIO locally, DO Spaces in prod)
    object_storage_endpoint: str = "http://localhost:9000"
    object_storage_bucket: str = "lexpar-case-files"

    # LiveKit real-time voice layer
    livekit_url: str = "ws://localhost:7880"
    livekit_api_key: str = "devkey"
    livekit_api_secret: str = "secret"

    # LLM routing (swappable per ARCHITECTURE §7)
    opposing_counsel_llm_provider: str = "fireworks"
    opposing_counsel_llm_endpoint: str = "https://api.fireworks.ai/inference/v1"
    judge_llm_provider: str = "fireworks"
    judge_llm_endpoint: str = "https://api.fireworks.ai/inference/v1"

    # Provider keys — unused by the REST API today; the agents worker will consume them.
    fireworks_api_key: str = ""
    deepgram_api_key: str = ""
    elevenlabs_api_key: str = ""

    # Auth. No insecure default: a blank/missing/weak JWT_SECRET fails loudly at startup (below)
    # rather than silently signing tokens with a guessable key.
    jwt_secret: str = ""
    auth_mode: str = "stub"

    # Scoped service credential for the agents worker (NOT user auth) — grants only the internal
    # session-write routes. Empty = no valid agent token (internal routes reject everything).
    agent_service_token: str = ""

    # CORS — comma-separated list of allowed browser origins (the frontend dev server).
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Token settings (not env-driven; sensible constants)
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 60

    @field_validator("jwt_secret")
    @classmethod
    def _require_strong_jwt_secret(cls, value: str) -> str:
        """Refuse to start unless JWT_SECRET is set to a strong signing key (fail loudly)."""
        cleaned = value.strip()
        if len(cleaned) < MIN_JWT_SECRET_LEN:
            raise ValueError(
                f"JWT_SECRET must be set to a strong secret of at least {MIN_JWT_SECRET_LEN} "
                "characters (generate one with: openssl rand -hex 32). Refusing to start with a "
                "blank, missing, or weak signing key."
            )
        return cleaned

    @property
    def cors_origin_list(self) -> list[str]:
        """CORS origins as a list, from the comma-separated env value."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()
