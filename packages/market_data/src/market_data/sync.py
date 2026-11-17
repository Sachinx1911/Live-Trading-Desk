"""Instrument master synchronisation from a provider into the canonical tables."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from market_data.repo.instruments import SyncResult, TokenFn, _default_token, upsert_instruments
from providers.base import MarketDataProvider

log = get_logger(__name__)


async def sync_instrument_master(
    provider: MarketDataProvider,
    session: AsyncSession,
    token_of: TokenFn | None = None,
) -> SyncResult:
    """Download the provider's instrument master and upsert it. Commits nothing; the caller
    owns the transaction. Providers may expose `provider_token(instrument)` for mapping."""
    instruments = await provider.fetch_instruments()
    fn: TokenFn = token_of or getattr(provider, "provider_token", None) or _default_token
    res = await upsert_instruments(session, instruments, provider.info.code, token_of=fn)
    log.info(
        "instruments.synced",
        provider=provider.info.code,
        new=res.new,
        updated=res.updated,
        unchanged=res.unchanged,
        skipped=res.skipped,
    )
    return res
