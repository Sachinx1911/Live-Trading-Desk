"""Application settings loaded from environment / .env. Documented in .env.example."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    log_json: bool = False

    database_url: str = "postgresql+asyncpg://trading:trading@localhost:5432/trading"
    database_url_sync: str = "postgresql+psycopg://trading:trading@localhost:5432/trading"
    redis_url: str = "redis://localhost:6379/0"

    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "minio"
    s3_secret_key: SecretStr = SecretStr("minio12345")
    s3_bucket: str = "trading-archive"

    secrets_key: SecretStr = SecretStr("CHANGE_ME_GENERATE_A_REAL_KEY")
    jwt_secret: SecretStr = SecretStr("CHANGE_ME_GENERATE_A_REAL_SECRET")
    jwt_access_ttl_seconds: int = 900
    jwt_refresh_ttl_seconds: int = 14 * 24 * 3600

    api_host: str = "0.0.0.0"  # noqa: S104 - bound inside containers; nginx fronts it
    api_port: int = 8000
    cors_origins: str = "http://localhost:3000"
    api_base_url: str = "http://localhost:8000"  # public URL of the API (OAuth redirects)
    web_base_url: str = "http://localhost:3000"  # where to send the user after broker login

    collect_raw_ticks: bool = False
    default_market_data_provider: Literal["fake", "upstox", "dhan"] = "fake"

    llm_provider: str = "openai"
    openai_api_key: SecretStr = SecretStr("")
    ai_daily_token_budget: int = 2_000_000

    telegram_bot_token: SecretStr = SecretStr("")
    telegram_chat_id: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def secrets_configured(self) -> bool:
        return not self.secrets_key.get_secret_value().startswith("CHANGE_ME") and not (
            self.jwt_secret.get_secret_value().startswith("CHANGE_ME")
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
