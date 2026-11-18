"""Historical replay sessions (ephemeral, in-process). See api.replay."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from api.deps import DB, User
from api.replay.manager import manager
from api.replay.session import MAX_SPEED, ReplaySession
from core.calendar import nse_calendar
from core.db.models import Strategy, StrategyVersion
from core.models import Timeframe
from core.time import IST, ensure_utc
from market_data.repo.candles import fetch_candles
from market_data.repo.instruments import get_instrument
from risk.limits import InstrumentMeta
from strategy.dsl.schema import StrategyDocument

router = APIRouter(prefix="/replay", tags=["replay"])


class SessionIn(BaseModel):
    instrument_id: int
    date: date
    timeframe: Timeframe = Timeframe.M1
    strategy_version_id: int | None = None
    speed: float = Field(default=10, gt=0, le=MAX_SPEED)
    seed: int | None = None


class SessionOut(BaseModel):
    session_id: str
    instrument_id: int
    date: date
    timeframe: Timeframe
    strategy_version_id: int | None
    bars: int
    first_ts: datetime | None
    last_ts: datetime | None
    warmup_bars: int
    state: dict[str, Any]


class ControlIn(BaseModel):
    action: str  # play | pause | step | seek | set_speed
    n: int | None = None
    ts: datetime | None = None
    speed: float | None = None


def _out(s: ReplaySession) -> SessionOut:
    return SessionOut(
        session_id=s.session_id,
        instrument_id=s.instrument_id,
        date=s.day,
        timeframe=s.timeframe,
        strategy_version_id=s.version_id,
        bars=len(s.bars),
        first_ts=s.bars[0].ts if s.bars else None,
        last_ts=s.bars[-1].ts if s.bars else None,
        warmup_bars=s.warmup_bars,
        state=s.state(),
    )


@router.post("/sessions", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
async def create_session(body: SessionIn, db: DB, user: User) -> SessionOut:
    await manager.sweep()
    cal = nse_calendar()
    bounds = cal.session_bounds_utc(body.date)
    if bounds is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{body.date} is not a trading day")
    start, end = bounds
    bars = await fetch_candles(
        db, body.instrument_id, Timeframe.M1, start, end + timedelta(minutes=1)
    )
    if not bars:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no 1-minute candles stored for that day")
    doc: StrategyDocument | None = None
    meta: InstrumentMeta | None = None
    warm: list[Any] = []
    if body.strategy_version_id is not None:
        v = await db.get(StrategyVersion, body.strategy_version_id)
        if v is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "strategy version not found")
        s = await db.get(Strategy, v.strategy_id)
        if s is None or s.user_id != user.user_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "strategy version not found")
        doc = StrategyDocument.model_validate(v.dsl)
        ins = await get_instrument(db, body.instrument_id)
        if ins is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "instrument not found")
        meta = InstrumentMeta(
            instrument_id=ins.instrument_id,
            symbol=ins.symbol,
            segment=ins.segment,
            lot_size=ins.lot_size,
            tick_size=ins.tick_size,
            underlying_symbol=ins.underlying_symbol,
        )
        warm = await fetch_candles(
            db, body.instrument_id, Timeframe.M1, start - timedelta(days=10), start
        )
    try:
        sess = manager.add(
            ReplaySession(
                user_id=user.user_id,
                instrument_id=body.instrument_id,
                day=body.date,
                timeframe=body.timeframe,
                candles_1m=bars,
                warmup_1m=warm,
                strategy=doc,
                strategy_version_id=body.strategy_version_id,
                meta=meta,
                speed=body.speed,
                seed=body.seed,
                calendar=cal,
            )
        )
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _out(sess)


@router.get("/sessions", response_model=list[SessionOut])
async def list_sessions(user: User) -> list[SessionOut]:
    await manager.sweep()
    return [_out(s) for s in manager.list_for(user.user_id)]


@router.get("/sessions/{session_id}", response_model=SessionOut)
async def get_session(session_id: str, user: User) -> SessionOut:
    s = manager.get(session_id, user.user_id)
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "replay session not found")
    return _out(s)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(session_id: str, user: User) -> None:
    if not await manager.remove(session_id, user.user_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "replay session not found")


@router.post("/sessions/{session_id}/control", response_model=dict[str, Any])
async def control_session(session_id: str, body: ControlIn, user: User) -> dict[str, Any]:
    s = manager.get(session_id, user.user_id)
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "replay session not found")
    msg: dict[str, Any] = {"action": body.action}
    if body.n is not None:
        msg["n"] = body.n
    if body.ts is not None:
        msg["ts"] = ensure_utc(body.ts).isoformat()
    if body.speed is not None:
        msg["speed"] = body.speed
    try:
        return await s.control(msg)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


__all__ = ["IST", "router"]
