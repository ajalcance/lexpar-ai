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
    object_storage_access_key: str = "minioadmin"
    object_storage_secret_key: str = "minioadmin"
    object_storage_region: str = "us-east-1"

    # Case-knowledge RAG (§12): Fireworks embeddings (OpenAI-compatible) + pleading upload limits.
    embedding_endpoint: str = "https://api.fireworks.ai/inference/v1"
    embedding_model: str = "nomic-ai/nomic-embed-text-v1.5"
    embedding_dim: int = 768
    case_summary_model: str = "accounts/fireworks/models/gpt-oss-120b"
    # Upload cap for pleadings (§12) and official rule documents (§13). Raised to 50: a large
    # text-based statute (hundreds of pages) runs ~5-15 MB, so 50 gives comfortable headroom while
    # still bounding memory (the route reads the whole file into RAM) and abuse. Not unbounded —
    # uploads are admin/attorney-gated and infrequent, not a public endpoint. Override via env
    # MAX_UPLOAD_MB. (Scanned/image PDFs are rejected at ingest for lacking extractable text, not by
    # size — a 30 MB scan and a 3 MB text copy of the same statute are handled very differently.)
    max_upload_mb: int = 50

    # Court-rule retrieval relevance floor (§13): cosine below this is treated as "not genuinely
    # relevant" and dropped — so retrieval returns FEWER than k, or zero, rather than padding in a
    # tenuous match (zero → the existing fail-open no-rules-block path). Start at 0.35 for
    # nomic-embed; tune on real data via RULE_RETRIEVAL_MIN_SCORE (unrelated text scores well below,
    # on-point rule text well above). Court rules only; pleading retrieval keeps no floor.
    rule_retrieval_min_score: float = 0.35

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
    # rather than silently signing tokens with a guessable key. There is only one auth mode now
    # (real bcrypt password auth) — the legacy AUTH_MODE=stub admin/admin path was removed at the
    # production cutover, so no auth_mode setting exists; a leftover AUTH_MODE in .env is ignored.
    jwt_secret: str = ""

    # Scoped service credential for the agents worker (NOT user auth) — grants only the internal
    # session-write routes. Empty = no valid agent token (internal routes reject everything).
    agent_service_token: str = ""

    # Self-service signup gate. Default True for local dev; set ALLOW_REGISTRATION=false on any
    # PUBLIC deployment once its accounts are provisioned — the register route is unauthenticated,
    # and every account it mints can burn GPU + provider credits (voice sessions are expensive).
    allow_registration: bool = True

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
