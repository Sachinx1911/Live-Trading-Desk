"""Bind a provider to canonical DB instrument ids after an instrument-master sync."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import InstrumentMapping
from market_data.repo._lookup import provider_id
from providers.base import MarketDataProvider


async def mapping_for(session: AsyncSession, provider_code: str) -> dict[int, str]:
    pid = await provider_id(session, provider_code)
    q = select(InstrumentMapping.instrument_id, InstrumentMapping.provider_token).where(
        InstrumentMapping.provider_id == pid, InstrumentMapping.valid_to.is_(None)
    )
    return {iid: tok for iid, tok in (await session.execute(q)).all()}


async def bind_provider(session: AsyncSession, provider: MarketDataProvider) -> int:
    """Teach the provider our DB ids (if it supports `bind_mapping`). Returns the count."""
    m = await mapping_for(session, provider.info.code)
    bind = getattr(provider, "bind_mapping", None)
    if callable(bind) and m:
        bind(m)
    return len(m)
