"""Option chain snapshots (ADR-010): whole-chain JSONB rows every few minutes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

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


@dataclass(frozen=True)
class ChainOi:
    """Total open interest per side of one stored chain snapshot (input to PCR)."""

    underlying_instrument_id: int
    expiry: datetime
    ts: datetime
    put_oi: int
    call_oi: int


def oi_totals(rows: list[dict[str, object]]) -> tuple[int, int]:
    """(put OI, call OI) summed over every strike of a snapshot's JSONB rows."""
    put = call = 0
    for r in rows:
        oi = r.get("oi")
        if not isinstance(oi, int | float) or oi <= 0:
            continue
        if r.get("option_type") == "PE":
            put += int(oi)
        elif r.get("option_type") == "CE":
            call += int(oi)
    return put, call


async def latest_chain_oi(
    session: AsyncSession, underlying_instrument_id: int, now: datetime
) -> ChainOi | None:
    """Newest non-empty snapshot of the nearest unexpired expiry, from the last day."""
    now = ensure_utc(now)
    q = (
        select(Row)
        .where(
            Row.underlying_instrument_id == underlying_instrument_id,
            Row.row_count > 0,
            Row.expiry >= now,
            Row.ts > now - timedelta(days=1),
            Row.ts <= now,
        )
        .order_by(Row.expiry.asc(), Row.ts.desc())
        .limit(1)
    )
    row = (await session.execute(q)).scalar_one_or_none()
    if row is None:
        return None
    put, call = oi_totals(row.rows)
    return ChainOi(row.underlying_instrument_id, row.expiry, row.ts, put, call)


async def chain_oi_for_option(
    session: AsyncSession, option_instrument_id: int, now: datetime
) -> ChainOi | None:
    """Chain OI of the underlying of one option contract (None if it is not a contract)."""
    underlying = (
        await session.execute(
            select(Contract.underlying_id).where(Contract.instrument_id == option_instrument_id)
        )
    ).scalar_one_or_none()
    if underlying is None:
        return None
    return await latest_chain_oi(session, underlying, now)
