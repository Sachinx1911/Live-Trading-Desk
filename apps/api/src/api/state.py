"""Process-wide resources: settings, redis, provider manager. Created once in lifespan."""

from __future__ import annotations

from dataclasses import dataclass

from redis.asyncio import Redis

from core.logging import get_logger
from core.settings import Settings
from providers.base import MarketDataProvider
from providers.registry import create as create_provider

log = get_logger(__name__)


@dataclass
class AppState:
    settings: Settings
    redis: Redis
    provider: MarketDataProvider

    @classmethod
    def create(cls, settings: Settings) -> AppState:
        return cls(
            settings=settings,
            redis=Redis.from_url(settings.redis_url, decode_responses=True),
            provider=create_provider(settings.default_market_data_provider),
        )

    async def startup(self) -> None:
        try:
            await self.provider.connect()
        except Exception as exc:
            log.warning("provider.connect_failed", provider=self.provider.info.code, error=str(exc))

    async def shutdown(self) -> None:
        try:
            await self.provider.disconnect()
        finally:
            await self.redis.aclose()
