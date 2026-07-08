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

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed view over the environment. Field names map case-insensitively to env vars."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

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

    # Auth
    jwt_secret: str = "dev-insecure-change-me"
    auth_mode: str = "stub"

    # Scoped service credential for the agents worker (NOT user auth) — grants only the internal
    # session-write routes. Empty = no valid agent token (internal routes reject everything).
    agent_service_token: str = ""

    # CORS — comma-separated list of allowed browser origins (the frontend dev server).
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Token settings (not env-driven; sensible constants)
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 60

    @property
    def cors_origin_list(self) -> list[str]:
        """CORS origins as a list, from the comma-separated env value."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()
