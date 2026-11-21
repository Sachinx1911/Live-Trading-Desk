"""Application settings loaded from environment / .env. Documented in .env.example."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
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
    collect_symbols: str = "NIFTY,BANKNIFTY,INDIAVIX"  # canonical symbols the collector follows
    collect_chain_underlyings: str = "NIFTY,BANKNIFTY"  # option-chain snapshots
    # Seconds between chain snapshots. The exchange refreshes OI about every 3 minutes,
    # so polling faster stores duplicates.
    collect_chain_interval_s: int = Field(default=180, ge=60, le=3600)
    data_dir: str = "data"  # Parquet archive root (raw ticks)
    live_trading_enabled: bool = False  # hard switch; gateway refuses everything when False
    paper_default_capital: int = 100_000  # ₹1,00,000 per master prompt, user-editable per account
    default_market_data_provider: Literal["fake", "upstox", "dhan"] = "fake"

    # Raw news ingest (Mark 1 Stage 3.5): comma-separated RSS/Atom URLs; empty = built-in
    # defaults (market_data.news.feeds.DEFAULT_FEEDS). Headlines + feed summary only.
    news_feeds: str = ""
    news_fetch_timeout_s: float = Field(default=15.0, ge=2, le=60)

    llm_provider: str = "openai"
    openai_api_key: SecretStr = SecretStr("")
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"
    ai_daily_token_budget: int = 2_000_000

    telegram_bot_token: SecretStr = SecretStr("")
    telegram_chat_id: str = ""

    # Proactive alerts (Mark 1 Stage 3.2): PCR distance from the pcr_guard thresholds that
    # counts as "near", and the window inside which the same alert is not stored again.
    alert_pcr_margin: float = Field(default=0.1, ge=0, le=1)
    alert_dedup_minutes: int = Field(default=30, ge=1, le=24 * 60)

    # Tool server for the owner's jarvis (Mark 1 Stage 4.1, docs/tool-server.md). Loopback by
    # default; LAN only if the owner sets the host. The highest level it serves is the lower of
    # this and the calling token's max_level (red is never served). Per-token rate limit.
    tool_server_host: str = "127.0.0.1"
    tool_server_port: int = Field(default=8100, ge=1, le=65535)
    tool_server_max_level: Literal["green", "yellow"] = "green"
    tool_server_rate_per_minute: int = Field(default=120, ge=1, le=6000)

    # JARVIS accuracy loop (Mark 1 Stage 4.6): a view is a hit when the close at its due date
    # moved at least this many percent its way (sideways: less than this either way). The
    # due-date close may arrive late; after this many trading days without it the view is void.
    view_score_threshold_pct: float = Field(default=1.0, gt=0, le=20)
    view_score_grace_days: int = Field(default=3, ge=0, le=20)

    # Local-dev convenience only: when set (and APP_ENV != production) POST /auth/dev-login
    # issues real tokens for this user without a password so the web app opens straight
    # on the dashboard. Refused at startup in production (see _refuse_dev_auto_login_in_prod).
    dev_auto_login_email: str = ""

    @model_validator(mode="after")
    def _refuse_dev_auto_login_in_prod(self) -> Settings:
        if self.dev_auto_login_email and self.app_env == "production":
            raise ValueError("DEV_AUTO_LOGIN_EMAIL must be empty when APP_ENV=production")
        return self

    @property
    def dev_auto_login_enabled(self) -> bool:
        return bool(self.dev_auto_login_email) and not self.is_production

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
