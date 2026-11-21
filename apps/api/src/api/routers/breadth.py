"""Daily market breadth (Mark 1 Stage 3.6): read stored rows; rebuilds run in the worker.
Rows come only from the active provider's daily candles; the response names it."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from api.audit import audit
from api.deps import DB, State, User
from core.db.models import MarketBreadth
from market_data.breadth.repo import latest_breadth, list_breadth
from market_data.breadth.universe import NIFTY50_AS_OF, NIFTY50_SOURCE, UNIVERSES

router = APIRouter(prefix="/market/breadth", tags=["market"])


class IndexMove(BaseModel):
    close: float | None
    prev_close: float | None
    change: float | None
    change_pct: float | None


class BreadthOut(BaseModel):
    as_of_date: date
    universe: str
    provider: str
    universe_size: int
    advances: int
    declines: int
    unchanged: int
    new_52w_high: int
    new_52w_low: int
    above_ema50_pct: float | None
    above_ema200_pct: float | None
    index_moves: dict[str, IndexMove]
    computed_at: datetime


class BreadthListOut(BaseModel):
    universe: str
    provider: str
    members: int
    membership_as_of: date
    membership_source: str
    rows: list[BreadthOut]


class RebuildIn(BaseModel):
    from_date: date
    to_date: date | None = None
    universe: str = Field("NIFTY50", max_length=40)


def _f(v: Decimal | None) -> float | None:
    return None if v is None else float(v)


def _out(r: MarketBreadth, provider: str) -> BreadthOut:
    moves: dict[str, Any] = r.index_moves or {}
    return BreadthOut(
        as_of_date=r.as_of_date,
        universe=r.universe,
        provider=provider,
        universe_size=r.universe_size,
        advances=r.advances,
        declines=r.declines,
        unchanged=r.unchanged,
        new_52w_high=r.new_52w_high,
        new_52w_low=r.new_52w_low,
        above_ema50_pct=_f(r.above_ema50_pct),
        above_ema200_pct=_f(r.above_ema200_pct),
        index_moves={k: IndexMove.model_validate(v) for k, v in moves.items()},
        computed_at=r.computed_at,
    )


def _universe(name: str) -> str:
    u = name.strip().upper()
    if u not in UNIVERSES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"unknown universe {name!r}")
    return u


@router.get("", response_model=BreadthListOut)
async def breadth(
    db: DB,
    state: State,
    _: User,
    universe: str = "NIFTY50",
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: date | None = None,
    limit: int = Query(250, ge=1, le=2000),
) -> BreadthListOut:
    u = _universe(universe)
    provider = state.settings.default_market_data_provider
    rows = await list_breadth(db, provider=provider, universe=u, start=from_, end=to, limit=limit)
    return BreadthListOut(
        universe=u,
        provider=provider,
        members=len(UNIVERSES[u]),
        membership_as_of=NIFTY50_AS_OF,
        membership_source=NIFTY50_SOURCE,
        rows=[_out(r, provider) for r in rows],
    )


@router.get("/latest", response_model=BreadthOut | None)
async def latest(db: DB, state: State, _: User, universe: str = "NIFTY50") -> BreadthOut | None:
    provider = state.settings.default_market_data_provider
    row = await latest_breadth(db, provider=provider, universe=_universe(universe))
    return _out(row, provider) if row else None


@router.post("/rebuild", status_code=status.HTTP_202_ACCEPTED)
async def rebuild(db: DB, state: State, user: User, body: RebuildIn) -> dict[str, str]:
    if not user.has_role("owner"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "owner only")
    u = _universe(body.universe)
    if body.to_date and body.to_date < body.from_date:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "to_date before from_date")
    pool = await create_pool(RedisSettings.from_dsn(state.settings.redis_url))
    try:
        await pool.enqueue_job(
            "rebuild_market_breadth",
            body.from_date.isoformat(),
            body.to_date.isoformat() if body.to_date else None,
            u,
        )
    finally:
        await pool.aclose()
    await audit(
        db,
        user_id=user.user_id,
        action="market.breadth.rebuild.enqueue",
        entity_type="market_breadth",
        after={"from": str(body.from_date), "to": str(body.to_date), "universe": u},
    )
    await db.commit()
    return {"status": "queued"}
