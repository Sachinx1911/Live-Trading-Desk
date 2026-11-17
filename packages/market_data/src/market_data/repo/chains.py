"""Option chain snapshots (ADR-010): whole-chain JSONB rows every few minutes."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import Contract
from core.db.models import OptionChainSnapshot as Row
from core.models import OptionChainSnapshot
from core.time import ensure_utc
from market_data.repo._lookup import provider_id


async def write_snapshot(session: AsyncSession, snap: OptionChainSnapshot) -> None:
    stmt = insert(Row).values(
        underlying_instrument_id=snap.underlying_instrument_id,
        expiry=ensure_utc(snap.expiry),
        ts=ensure_utc(snap.ts),
        provider_id=await provider_id(session, snap.provider_id),
        underlying_price=snap.underlying_price,
        row_count=len(snap.rows),
        rows=[r.model_dump(mode="json") for r in snap.rows],
        provider_ts=snap.provider_ts,
    )
    stmt = stmt.on_conflict_do_nothing(
        index_elements=["underlying_instrument_id", "expiry", "ts", "provider_id"]
    )
    await session.execute(stmt)


async def latest_snapshot(
    session: AsyncSession, underlying_instrument_id: int, expiry: datetime | None = None
) -> Row | None:
    q = (
        select(Row)
        .where(Row.underlying_instrument_id == underlying_instrument_id)
        .order_by(Row.ts.desc())
        .limit(1)
    )
    if expiry is not None:
        q = q.where(Row.expiry == ensure_utc(expiry))
    return (await session.execute(q)).scalar_one_or_none()


async def expiries_for(
    session: AsyncSession, underlying_instrument_id: int, on_or_after: date
) -> list[date]:
    q = (
        select(Contract.expiry)
        .where(Contract.underlying_id == underlying_instrument_id, Contract.expiry >= on_or_after)
        .distinct()
        .order_by(Contract.expiry)
    )
    return [d for (d,) in (await session.execute(q)).all()]
