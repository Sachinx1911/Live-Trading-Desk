"""Market regime (Module 6): today's regime, intraday day type and history per instrument."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Annotated, Any

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from api.audit import audit
from api.deps import DB, State, User
from core.time import IST, utcnow
from market_data.repo.instruments import get_by_symbol, get_instrument
from market_data.repo.regime import fetch_daily, latest_daily, latest_intraday

router = APIRouter(prefix="/market/regime", tags=["regime"])


class RegimeDailyOut(BaseModel):
    date: date
    trend: str
    strength: str
    volatility: str
    structure: str
    adx: float | None
    ema20: float | None
    ema50: float | None
    ema200: float | None
    atr_pct: float | None
    vix: float | None
    vix_percentile: float | None
    event_day: bool
    events: list[str]
    computed_at: datetime | None
    label: str


class RegimeIntradayOut(BaseModel):
    ts: datetime
    day_type: str
    or_high: float | None
    or_low: float | None
    vwap_distance_pct: float | None
    atr_ratio: float | None


class RegimeOut(BaseModel):
    instrument_id: int
    symbol: str
    today: RegimeDailyOut | None
    intraday: RegimeIntradayOut | None
    history: list[RegimeDailyOut] = []


def _daily_out(r: Any) -> RegimeDailyOut:
    d = r.as_dict()
    return RegimeDailyOut(
        date=r.date,
        trend=d["trend"],
        strength=d["strength"],
        volatility=d["volatility"],
        structure=d["structure"],
        adx=d["adx"],
        ema20=d["ema20"],
        ema50=d["ema50"],
        ema200=d["ema200"],
        atr_pct=d["atr_pct"],
        vix=d["vix"],
        vix_percentile=d["vix_percentile"],
        event_day=d["event_day"],
        events=d["events"],
        computed_at=r.computed_at,
        label=r.label,
    )


def _intraday_out(r: Any) -> RegimeIntradayOut:
    return RegimeIntradayOut(
        ts=r.ts,
        day_type=r.day_type,
        or_high=r.or_high,
        or_low=r.or_low,
        vwap_distance_pct=r.vwap_distance_pct,
        atr_ratio=r.atr_ratio,
    )


async def _regime_for(db: DB, instrument_id: int, symbol: str, days: int) -> RegimeOut:
    today = utcnow().astimezone(IST).date()
    latest = await latest_daily(db, instrument_id)
    intra = await latest_intraday(db, instrument_id, today)
    history = (
        await fetch_daily(db, instrument_id, today - timedelta(days=days), today) if days else []
    )
    return RegimeOut(
        instrument_id=instrument_id,
        symbol=symbol,
        today=_daily_out(latest) if latest else None,
        intraday=_intraday_out(intra) if intra else None,
        history=[_daily_out(r) for r in history],
    )


@router.get("/summary", response_model=list[RegimeOut])
async def regime_summary(db: DB, state: State, _: User) -> list[RegimeOut]:
    """Today's regime for the tracked index symbols (NIFTY, BANKNIFTY ...)."""
    out: list[RegimeOut] = []
    symbols = [s.strip().upper() for s in state.settings.collect_symbols.split(",") if s.strip()]
    for sym in symbols:
        ins = await get_by_symbol(db, "NSE", sym)
        if ins is None or ins.segment.value in ("options", "futures"):
            continue
        out.append(await _regime_for(db, ins.instrument_id, ins.symbol, 0))
    return out


@router.get("", response_model=RegimeOut)
async def regime(
    db: DB, _: User, instrument_id: int, days: Annotated[int, Query(ge=0, le=400)] = 30
) -> RegimeOut:
    ins = await get_instrument(db, instrument_id)
    if ins is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "instrument not found")
    return await _regime_for(db, instrument_id, ins.symbol, days)


@router.post("/recompute", status_code=status.HTTP_202_ACCEPTED)
async def recompute(db: DB, state: State, user: User, day: date | None = None) -> dict[str, str]:
    if not user.has_role("owner"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "owner only")
    pool = await create_pool(RedisSettings.from_dsn(state.settings.redis_url))
    try:
        await pool.enqueue_job("compute_regime_daily", day.isoformat() if day else None)
    finally:
        await pool.aclose()
    await audit(
        db,
        user_id=user.user_id,
        action="regime.recompute",
        entity_type="regime",
        entity_id=str(day) if day else "latest",
    )
    await db.commit()
    return {"status": "queued", "day": day.isoformat() if day else "latest"}
