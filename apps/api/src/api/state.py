"""Process-wide resources: settings, redis, provider manager. Created once in lifespan."""

from __future__ import annotations

from dataclasses import dataclass, field

from redis.asyncio import Redis

from ai.llm import DailyTokenBudget, LLMProvider, build_provider
from ai.repo import DbAiCallLogger
from core.logging import get_logger
from core.notify import Notifier, build_notifier
from core.secrets import SecretBox
from core.settings import Settings
from providers.base import MarketDataProvider
from providers.registry import create as create_provider

log = get_logger(__name__)


@dataclass
class AppState:
    settings: Settings
    redis: Redis
    provider: MarketDataProvider
    notifier: Notifier
    secret_box: SecretBox | None
    broker_tokens: dict[str, str] = field(default_factory=dict)  # code -> decrypted token
    llm: LLMProvider | None = None  # None = AI not configured; routes answer 503 honestly
    ai_logger: DbAiCallLogger = field(default_factory=DbAiCallLogger)
    ai_daily: DailyTokenBudget | None = None

    @classmethod
    def create(cls, settings: Settings) -> AppState:
        box: SecretBox | None
        try:
            box = SecretBox(settings.secrets_key.get_secret_value())
        except ValueError:
            box = None
            log.warning("secrets.not_configured")
        state = cls(
            settings=settings,
            redis=Redis.from_url(settings.redis_url, decode_responses=True),
            provider=create_provider("fake"),
            notifier=build_notifier(settings),
            secret_box=box,
        )
        state.llm = build_provider(settings)
        state.ai_daily = DailyTokenBudget(state.redis, settings.ai_daily_token_budget)
        if settings.default_market_data_provider == "upstox":
            from providers.upstox.provider import UpstoxMarketDataProvider

            state.provider = UpstoxMarketDataProvider(
                access_token_getter=lambda: state.broker_tokens.get("upstox")
            )
        elif settings.default_market_data_provider != "fake":
            state.provider = create_provider(settings.default_market_data_provider)
        return state

    async def load_broker_tokens(self) -> None:
        """Pull the current valid broker tokens from the DB into memory (startup + cron)."""
        if self.secret_box is None:
            return
        from sqlalchemy import select

        from core.db import get_session_factory
        from core.db.models import Broker, BrokerAccount
        from core.services.brokers import BrokerService

        async with get_session_factory()() as db:
            svc = BrokerService(db, self.settings, self.secret_box)
            rows = await db.execute(
                select(BrokerAccount, Broker.code)
                .join(Broker, Broker.id == BrokerAccount.broker_id)
                .where(BrokerAccount.is_active.is_(True))
            )
            for acct, code in rows.all():
                tok = await svc.valid_token(acct.id)
                if tok:
                    self.broker_tokens[code] = tok
                else:
                    self.broker_tokens.pop(code, None)
            await db.commit()

    async def startup(self) -> None:
        try:
            await self.load_broker_tokens()
        except Exception as exc:
            log.warning("broker_tokens.load_failed", error=str(exc))
        try:
            await self.provider.connect()
        except Exception as exc:
            log.warning("provider.connect_failed", provider=self.provider.info.code, error=str(exc))

    async def shutdown(self) -> None:
        try:
            await self.provider.disconnect()
        finally:
            await self.redis.aclose()
