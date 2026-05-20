"""Application configuration via pydantic-settings.

All settings are loaded from environment variables (and .env file in dev).
No secrets may appear in source code — see .env.example for all required vars.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -------------------------------------------------------------------------
    # Database
    # -------------------------------------------------------------------------
    database_url: str = Field(..., description="asyncpg-compatible PostgreSQL DSN")
    clickhouse_host: str = Field("localhost", description="ClickHouse hostname")
    clickhouse_port: int = Field(9000, description="ClickHouse native port")
    redis_url: str = Field("redis://localhost:6379/0", description="Redis DSN")

    # -------------------------------------------------------------------------
    # JWT authentication
    # -------------------------------------------------------------------------
    api_secret_key: str = Field(..., description="HS256 signing secret for JWTs")
    jwt_algorithm: str = Field("HS256", description="JWT signing algorithm")
    jwt_expire_minutes: int = Field(60, description="Token validity window in minutes")

    # -------------------------------------------------------------------------
    # Admin bootstrap
    # -------------------------------------------------------------------------
    harmoni_admin_token: str = Field(
        ..., description="Static bearer token for tenant provisioning endpoints"
    )

    # -------------------------------------------------------------------------
    # Rate limiting
    # -------------------------------------------------------------------------
    rate_limit_rpm_default: int = Field(
        60, description="Default max requests per minute per tenant"
    )
    rate_limit_enabled: bool = Field(True, description="Toggle rate limiting (disable in tests)")

    # -------------------------------------------------------------------------
    # CORS
    # -------------------------------------------------------------------------
    api_allowed_origins: str = Field(
        "http://localhost:3000",
        description="Comma-separated list of allowed CORS origins",
    )

    @field_validator("api_allowed_origins", mode="before")
    @classmethod
    def coerce_origins(cls, v: str) -> str:
        return v.strip()

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.api_allowed_origins.split(",") if o.strip()]

    # -------------------------------------------------------------------------
    # Webhook dispatch
    # -------------------------------------------------------------------------
    webhook_timeout_seconds: float = Field(5.0, description="HTTP timeout for outbound webhooks")
    webhook_max_retries: int = Field(3, description="Max delivery attempts per event")

    # -------------------------------------------------------------------------
    # Feature flags
    # -------------------------------------------------------------------------
    feature_rl_orchestrator: bool = Field(
        False, description="Enable RL-based NBA policy (research only)"
    )

    # -------------------------------------------------------------------------
    # Observability
    # -------------------------------------------------------------------------
    log_level: str = Field("INFO", description="Root logger level")
    log_json: bool = Field(True, description="Emit structured JSON logs")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the singleton Settings instance (cached after first call)."""
    return Settings()  # type: ignore[call-arg]
