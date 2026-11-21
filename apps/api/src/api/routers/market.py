"""Instruments, candles, quotes, option chain, coverage. Everything carries source and
freshness; nothing here invents a price."""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Annotated, Any

import orjson
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from api.deps import DB, State, User
from core.models import Candle, Freshness, Instrument, Quote, Timeframe
from core.time import IST, ensure_utc, utcnow
from market_data.oi_change import compare_chains, expiries_on_day, pcr, snapshot_pair
from market_data.repo._lookup import provider_id
from market_data.repo.candles import coverage, fetch_candles
from market_data.repo.chains import expiries_for, latest_snapshot
from market_data.repo.instruments import get_instrument, search
from market_data.repo.quotes import get_cached_quotes

router = APIRouter(tags=["market"])


class CandlesOut(BaseModel):
    instrument_id: int
    timeframe: Timeframe
    source: str
    is_demo: bool
    freshness: Freshness
    candles: list[Candle]


class QuotesOut(BaseModel):
    quotes: dict[int, Quote]
    missing: list[int]
    as_of: datetime


class CoverageOut(BaseModel):
    instrument_id: int
    timeframe: str
    provider: str
    first_ts: datetime | None
    last_ts: datetime | None
    rows: int


class ChainOut(BaseModel):
    underlying_instrument_id: int
    expiry: datetime
    ts: datetime
    source: str
    freshness: Freshness
    underlying_price: Decimal | None
    rows: list[dict[str, Any]]


class CollectorHealth(BaseModel):
    running: bool
    detail: dict[str, Any] | None


@router.get("/instruments", response_model=list[Instrument])
async def search_instruments(
    db: DB,
    _: User,
    q: Annotated[str, Query(min_length=1, max_length=64)],
    exchange: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[Instrument]:
    return await search(db, q, limit=limit, exchange=exchange)


@router.get("/instruments/{instrument_id}", response_model=Instrument)
async def instrument(instrument_id: int, db: DB, _: User) -> Instrument:
    ins = await get_instrument(db, instrument_id)
    if ins is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "instrument not found")
    return ins


@router.get("/market/candles", response_model=CandlesOut)
async def candles(
    db: DB,
    state: State,
    _: User,
    instrument_id: int,
    timeframe: Timeframe = Timeframe.M5,
    start: datetime | None = None,
    end: datetime | None = None,
    provider: str | None = None,
    limit: Annotated[int, Query(ge=1, le=5000)] = 1000,
) -> CandlesOut:
    end_dt = ensure_utc(end) if end else utcnow()
    if start is None:
        dur = timeframe.duration
        span = (dur * limit * 2) if dur else None
        start_dt = (end_dt - span) if span else end_dt.replace(year=end_dt.year - 10)
    else:
        start_dt = ensure_utc(start)
    # Never mix providers in one series: default to the active provider's rows.
    provider = provider or state.provider.info.code
    rows = await fetch_candles(db, instrument_id, timeframe, start_dt, end_dt, provider)
    rows = rows[-limit:]
    src = rows[-1].provider_id if rows else (provider or state.provider.info.code)
    is_demo = any(c.is_demo for c in rows)
    return CandlesOut(
        instrument_id=instrument_id,
        timeframe=timeframe,
        source=src,
        is_demo=is_demo,
        freshness=Freshness.DEMO if is_demo else Freshness.HISTORICAL,
        candles=rows,
    )


@router.get("/market/quotes", response_model=QuotesOut)
async def quotes(state: State, _: User, ids: Annotated[str, Query(min_length=1)]) -> QuotesOut:
    """Latest quotes from the Redis cache written by the collector. Missing ids mean the
    collector has not seen that instrument: the UI shows Disconnected, never a stale number."""
    try:
        want = [int(x) for x in ids.split(",") if x.strip()]
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "ids must be integers") from exc
    now = utcnow()
    found = await get_cached_quotes(state.redis, want, now)
    return QuotesOut(quotes=found, missing=[i for i in want if i not in found], as_of=now)


@router.get("/market/coverage", response_model=list[CoverageOut])
async def data_coverage(db: DB, _: User, instrument_id: int | None = None) -> list[CoverageOut]:
    return [
        CoverageOut(
            instrument_id=r.instrument_id,
            timeframe=str(r.timeframe),
            provider=r.provider_code,
            first_ts=r.first_ts,
            last_ts=r.last_ts,
            rows=r.count,
        )
        for r in await coverage(db, instrument_id)
    ]


@router.get("/market/option-chain/expiries", response_model=list[date])
async def chain_expiries(db: DB, _: User, underlying_id: int) -> list[date]:
    return await expiries_for(db, underlying_id, utcnow().astimezone(IST).date())


@router.get("/market/option-chain", response_model=ChainOut)
async def option_chain(
    db: DB, _: User, underlying_id: int, expiry: datetime | None = None, at: datetime | None = None
) -> ChainOut:
    """Latest stored snapshot (collector writes every few minutes), or with `at` the last one
    stored at or before that moment (Greeks and OI of an earlier time). Live provider calls are
    not made from the API so a slow broker cannot block the UI."""
    snap = await latest_snapshot(db, underlying_id, expiry, at)
    if snap is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no option chain snapshot yet")
    from market_data.repo._lookup import provider_code

    code = await provider_code(db, snap.provider_id)
    age = (utcnow() - snap.ts).total_seconds()
    if code == "fake":
        fresh = Freshness.DEMO
    elif at is not None:
        fresh = Freshness.HISTORICAL
    else:
        fresh = Freshness.DELAYED if age < 600 else Freshness.STALE
    return ChainOut(
        underlying_instrument_id=snap.underlying_instrument_id,
        expiry=snap.expiry,
        ts=snap.ts,
        source=code,
        freshness=fresh,
        underlying_price=snap.underlying_price,
        rows=snap.rows,
    )


class OiStrikeOut(BaseModel):
    strike: Decimal
    call_oi_from: int | None
    call_oi_to: int | None
    call_change: int | None
    put_oi_from: int | None
    put_oi_to: int | None
    put_change: int | None


class OiChangeOut(BaseModel):
    """OI change between two stored snapshots of one day (Mark 1, 1.2). `from_ts` / `to_ts`
    are the snapshots actually used; the UI shows their distance to the requested times."""

    underlying_instrument_id: int
    expiry: date
    day: date
    requested_from: datetime
    requested_to: datetime
    from_ts: datetime
    to_ts: datetime
    source: str
    freshness: Freshness
    spot_from: Decimal | None
    spot_to: Decimal | None
    pcr_from: Decimal | None
    pcr_to: Decimal | None
    call_oi_change_total: int
    put_oi_change_total: int
    strikes: list[OiStrikeOut]


def _ist_at(day: date, hhmm: str) -> datetime:
    try:
        t = time.fromisoformat(hhmm)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"bad time {hhmm!r}") from exc
    return ensure_utc(datetime.combine(day, t, tzinfo=IST))


@router.get("/market/oi-change/expiries", response_model=list[date])
async def oi_change_expiries(
    db: DB, state: State, _: User, underlying_id: int, day: date | None = None
) -> list[date]:
    """Expiries with stored snapshots on `day` (IST, default today) for the active provider."""
    d = day or utcnow().astimezone(IST).date()
    pid = await provider_id(db, state.provider.info.code)
    return await expiries_on_day(db, underlying_id, pid, d)


@router.get("/market/oi-change", response_model=OiChangeOut)
async def oi_change(
    db: DB,
    state: State,
    _: User,
    underlying_id: int,
    expiry: date,
    day: date | None = None,
    start: Annotated[str, Query(pattern=r"^\d{2}:\d{2}$")] = "09:15",
    end: Annotated[str, Query(pattern=r"^\d{2}:\d{2}$")] = "15:30",
) -> OiChangeOut:
    """Per-strike call/put OI change between the first stored snapshot at or after `start`
    and the last at or before `end` (IST times on `day`), active provider only."""
    now = utcnow()
    d = day or now.astimezone(IST).date()
    t_from, t_to = _ist_at(d, start), _ist_at(d, end)
    if t_to <= t_from:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "end must be after start")
    code = state.provider.info.code
    pid = await provider_id(db, code)
    pair = await snapshot_pair(db, underlying_id, expiry, pid, t_from, min(t_to, now))
    if pair is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "no option chain snapshot stored in this window"
        )
    a, b = pair.start, pair.end
    strikes = compare_chains(a.rows, b.rows)
    if code == "fake":
        fresh = Freshness.DEMO
    elif d != now.astimezone(IST).date():
        fresh = Freshness.HISTORICAL
    else:
        fresh = Freshness.DELAYED if (now - b.ts).total_seconds() < 600 else Freshness.STALE
    return OiChangeOut(
        underlying_instrument_id=underlying_id,
        expiry=expiry,
        day=d,
        requested_from=t_from,
        requested_to=t_to,
        from_ts=a.ts,
        to_ts=b.ts,
        source=code,
        freshness=fresh,
        spot_from=a.underlying_price,
        spot_to=b.underlying_price,
        pcr_from=pcr(a.rows),
        pcr_to=pcr(b.rows),
        call_oi_change_total=sum(s.call_change or 0 for s in strikes),
        put_oi_change_total=sum(s.put_change or 0 for s in strikes),
        strikes=[
            OiStrikeOut(
                strike=s.strike,
                call_oi_from=s.call_oi_from,
                call_oi_to=s.call_oi_to,
                call_change=s.call_change,
                put_oi_from=s.put_oi_from,
                put_oi_to=s.put_oi_to,
                put_change=s.put_change,
            )
            for s in strikes
        ],
    )


@router.get("/market/collector", response_model=CollectorHealth)
async def collector_health(state: State, _: User) -> CollectorHealth:
    raw = await state.redis.get("collector:health")
    if raw is None:
        return CollectorHealth(running=False, detail=None)
    return CollectorHealth(running=True, detail=orjson.loads(raw))
