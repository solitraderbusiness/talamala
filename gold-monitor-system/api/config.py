"""
Application configuration loaded from environment variables.

Uses Pydantic Settings for validation and type coercion.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration — every value can be overridden via env vars."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Database ────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://gold:gold@db:5432/gold_monitor"
    DATABASE_URL_SYNC: str = "postgresql+psycopg2://gold:gold@db:5432/gold_monitor"

    # ── Redis ───────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://redis:6379/0"

    # ── LLM / OpenRouter ───────────────────────────────────────────────
    OPENROUTER_API_KEY: str = ""

    # ── Security ────────────────────────────────────────────────────────
    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # ── Default admin credentials (seeded on first run) ─────────────────
    ADMIN_EMAIL: str = "admin@gold.local"
    ADMIN_PASSWORD: str = "changeme"

    # ── Rule engine ─────────────────────────────────────────────────────
    YAML_PATH: str = "/app/gold_monitor_rules_fa.yaml"


settings = Settings()
