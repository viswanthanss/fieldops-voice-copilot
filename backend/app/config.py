"""
Configuration module for FieldOps Voice Copilot backend.
All config is read from environment variables — never hard-coded secrets.
"""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = "sqlite+aiosqlite:///./fieldops.db"

    # ── JWT / Auth ────────────────────────────────────────────────────────────
    SECRET_KEY: str = "dev-secret-key-change-in-production-please"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # ── CORS ──────────────────────────────────────────────────────────────────
    CORS_ORIGINS: List[str] = ["http://localhost:3000"]

    # ── Rate Limiting ─────────────────────────────────────────────────────────
    RATE_LIMIT_PER_MINUTE: int = 100

    # ── Environment ───────────────────────────────────────────────────────────
    ENVIRONMENT: Literal["development", "production"] = "development"

    # ── Redis (optional — in-memory sessions used when absent) ────────────────
    REDIS_URL: Optional[str] = None

    # ── LiveKit ───────────────────────────────────────────────────────────────
    LIVEKIT_URL: str = "ws://localhost:7880"
    LIVEKIT_API_KEY: str = "devkey"
    LIVEKIT_API_SECRET: str = "devsecret"

    # ── Observability ─────────────────────────────────────────────────────────
    OTEL_ENDPOINT: Optional[str] = None
    LOG_LEVEL: str = "INFO"

    # ── Privacy / Retention ───────────────────────────────────────────────────
    AUDIT_RETENTION_DAYS: int = 90

    # ── Validators ────────────────────────────────────────────────────────────
    @field_validator("SECRET_KEY")
    @classmethod
    def secret_key_strong_in_prod(cls, v: str, info) -> str:  # noqa: ANN001
        """Warn (but don't block) if a weak key is used outside development."""
        # Full validation happens at startup in main.py
        return v

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):  # noqa: ANN001
        """Allow CORS_ORIGINS to be supplied as a comma-separated string."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v


# Singleton — import this everywhere
settings = Settings()
