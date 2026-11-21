"""Option chain snapshots (ADR-010): whole-chain JSONB rows every few minutes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import Contract
from core.db.models import OptionChainSnapshot as Row
from core.models import Instrument, OptionChainSnapshot
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
    session: AsyncSession,
    underlying_instrument_id: int,
    expiry: datetime | None = None,
    at: datetime | None = None,
) -> Row | None:
    """Newest stored snapshot, or the newest at or before `at` (never a later one)."""
    q = (
        select(Row)
        .where(Row.underlying_instrument_id == underlying_instrument_id)
        .order_by(Row.ts.desc())
        .limit(1)
    )
    if expiry is not None:
        q = q.where(Row.expiry == ensure_utc(expiry))
    if at is not None:
        q = q.where(Row.ts <= ensure_utc(at))
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


async def chain_oi_history(
    session: AsyncSession,
    underlying_instrument_id: int,
    start: datetime,
    end: datetime,
    provider: str | None = None,
) -> list[ChainOi]:
    """Chain OI totals of every stored snapshot in [start, end], one point per snapshot time,
    taken from the nearest expiry not yet expired at that time (same choice as
    `latest_chain_oi`). Totals are summed in SQL with the same rule as `oi_totals` (only
    positive OI counts). `provider` (code) keeps one source; None means any."""
    from sqlalchemy import text

    pid = await provider_id(session, provider) if provider else None
    q = text(
        """
        SELECT s.ts, s.expiry,
               COALESCE(SUM(CASE WHEN r->>'option_type' = 'PE' AND (r->>'oi')::numeric > 0
                                 THEN (r->>'oi')::numeric END), 0)::bigint AS put_oi,
               COALESCE(SUM(CASE WHEN r->>'option_type' = 'CE' AND (r->>'oi')::numeric > 0
                                 THEN (r->>'oi')::numeric END), 0)::bigint AS call_oi
        FROM option_chain_snapshots s
        CROSS JOIN LATERAL jsonb_array_elements(s.rows) AS r
        WHERE s.underlying_instrument_id = :und
          AND s.row_count > 0
          AND s.ts >= :start AND s.ts <= :end
          AND s.expiry >= s.ts
          AND (CAST(:pid AS bigint) IS NULL OR s.provider_id = :pid)
          AND jsonb_typeof(r->'oi') = 'number'
        GROUP BY s.ts, s.expiry
        ORDER BY s.ts, s.expiry
        """
    )
    rows = (
        await session.execute(
            q,
            {
                "und": underlying_instrument_id,
                "start": ensure_utc(start),
                "end": ensure_utc(end),
                "pid": pid,
            },
        )
    ).all()
    out: dict[datetime, ChainOi] = {}
    for ts, expiry, put_oi, call_oi in rows:
        if ts in out:  # rows are ordered by expiry: the first one per ts is the nearest
            continue
        out[ts] = ChainOi(underlying_instrument_id, expiry, ts, int(put_oi), int(call_oi))
    return list(out.values())


async def chain_underlying_id(session: AsyncSession, instrument: Instrument) -> int | None:
    """Instrument whose option chain describes `instrument`: itself for an index, the
    underlying for an option or future contract; None when unknown."""
    from core.models import Segment
    from market_data.repo.instruments import get_by_symbol

    if instrument.segment == Segment.INDEX:
        return instrument.instrument_id
    if instrument.segment not in (Segment.OPTIONS, Segment.FUTURES):
        return None
    if not instrument.underlying_symbol:
        return None
    und = await get_by_symbol(session, instrument.exchange, instrument.underlying_symbol)
    return und.instrument_id if und is not None else None


async def underlying_chain_oi_history(
    session: AsyncSession,
    instrument: Instrument,
    start: datetime,
    end: datetime,
    provider: str | None = None,
) -> list[ChainOi]:
    """`chain_oi_history` of the underlying of an option contract (Mark 1, Stage 2), with a
    day of lead-in before `start` so the first bars can see the previous session's last value.
    Empty for anything that is not an option or whose underlying is unknown."""
    from core.models import Segment

    if instrument.segment != Segment.OPTIONS:
        return []
    und = await chain_underlying_id(session, instrument)
    if und is None:
        return []
    return await chain_oi_history(session, und, start - timedelta(days=1), end, provider)


async def chain_snapshots_between(
    session: AsyncSession,
    underlying_instrument_id: int,
    start: datetime,
    end: datetime,
    provider: str | None = None,
) -> list[tuple[datetime, Decimal | None, list[dict[str, Any]]]]:
    """(ts, spot, rows) of every non-empty stored snapshot in [start, end], one per time,
    from the nearest expiry not yet expired at that time; one provider when given. Input to
    the DSL `option` operand in simulations (strategy.option_features.ChainHistory)."""
    pid = await provider_id(session, provider) if provider else None
    q = (
        select(Row.ts, Row.expiry, Row.underlying_price, Row.rows)
        .where(
            Row.underlying_instrument_id == underlying_instrument_id,
            Row.row_count > 0,
            Row.ts >= ensure_utc(start),
            Row.ts <= ensure_utc(end),
            Row.expiry >= Row.ts,
        )
        .order_by(Row.ts, Row.expiry)
    )
    if pid is not None:
        q = q.where(Row.provider_id == pid)
    out: dict[datetime, tuple[datetime, Decimal | None, list[dict[str, Any]]]] = {}
    for ts, _expiry, spot, rows in (await session.execute(q)).all():
        if ts not in out:  # ordered by expiry: first per time is the nearest
            out[ts] = (ts, spot, rows)
    return list(out.values())
