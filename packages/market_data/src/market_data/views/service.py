"""`record_view`: store one directional market view of JARVIS with an honest reference price.

Tool-server contract (Mark 1 Stage 4.1 / 4.6): this is a plain async function with a Pydantic
input model, so the tool server can register it unchanged::

    out: RecordViewOut = await record_view(db, redis, settings, RecordViewIn(...))

- `db` is an `AsyncSession`; the function commits by default (`commit=False` only flushes,
  for callers that own the transaction).
- `redis` may be `None` (then only stored candles are used) or a redis.asyncio client
  returning `str` or `bytes`.
- Failure is `ViewRefused` (a `ValueError`) with a stable `code`: `unknown_instrument` or
  `no_reference_price`. Nothing is stored when it is raised.

The reference price is taken here, at this moment, never from the caller. Candidates:

- the quote in the Redis quote cache the collector writes (`quote:<instrument_id>`), with its
  own freshness (live / delayed / stale / demo) and `ref_ts` = the quote's time;
- the newest stored 1m and 1d candle closes of the active provider
  (`DEFAULT_MARKET_DATA_PROVIDER`), freshness `historical` (or `demo` for a demo provider),
  `ref_ts` = the moment that bar closed. A daily bar whose session has not closed yet is
  not used.

The most recent candidate by `ref_ts` wins (the collector keeps the last quote cached for
days, so a cached quote is not automatically newer than a stored close); on a tie the quote
wins. The source and freshness are recorded as they are, e.g. `upstox:quote` / `stale`.

No price at all = no observation. Observations are append-only and are never read by any
strategy, risk check or order path (ADR-009; enforced by an import-linter contract).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.calendar import nse_calendar
from core.db.models import AiObservation, DataProvider, HistoricalCandle
from core.models import Freshness, Timeframe
from core.settings import Settings
from core.time import ensure_utc, utcnow
from market_data.repo.instruments import get_by_symbol
from market_data.repo.quotes import get_cached_quote
from market_data.views.scoring import due_date

RefusalCode = Literal["unknown_instrument", "no_reference_price"]


class ViewRefused(ValueError):  # noqa: N818 - a refusal, not a crash
    def __init__(self, code: RefusalCode, message: str) -> None:
        super().__init__(message)
        self.code = code


class RecordViewIn(BaseModel):
    """One directional view. Prices are never accepted from the caller except the optional
    invalidation level, which is the caller's own condition."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    symbol: str = Field(min_length=1, max_length=40, description="Canonical symbol, e.g. NIFTY")
    exchange: str = Field("NSE", min_length=2, max_length=10)
    direction: Literal["up", "down", "sideways"]
    horizon_days: int = Field(ge=1, le=250, description="Horizon in NSE trading days")
    confidence: Decimal = Field(ge=0, le=1, max_digits=4, decimal_places=3)
    invalidation: str | None = Field(
        None, max_length=500, description='e.g. "view wrong below 23,800"'
    )
    invalidation_price: Decimal | None = Field(None, gt=0, max_digits=14, decimal_places=4)
    statement: str | None = Field(None, max_length=4000)
    caller: str = Field(min_length=1, max_length=40, pattern=r"^[a-z0-9_.-]+$")
    mode: str | None = Field(None, max_length=20, pattern=r"^[a-z0-9_.-]+$")
    tool_call_id: int | None = Field(None, ge=1)

    @field_validator("symbol", "exchange")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()


class RecordViewOut(BaseModel):
    observation_id: int
    ts: datetime
    symbol: str
    instrument_id: int
    direction: str
    horizon_days: int
    confidence: Decimal
    due_date: date
    ref_price: Decimal
    ref_source: str
    ref_freshness: str
    ref_ts: datetime
    is_demo: bool
    invalidation: str | None
    invalidation_price: Decimal | None
    warnings: list[str]


@dataclass(frozen=True)
class RefPrice:
    price: Decimal
    source: str
    freshness: str
    ts: datetime
    is_demo: bool


async def _latest_candle(
    db: AsyncSession, instrument_id: int, provider: str, tf: Timeframe
) -> tuple[HistoricalCandle, bool] | None:
    q = (
        select(HistoricalCandle, DataProvider.is_demo)
        .join(DataProvider, DataProvider.id == HistoricalCandle.provider_id)
        .where(
            HistoricalCandle.instrument_id == instrument_id,
            HistoricalCandle.timeframe == tf,
            DataProvider.code == provider,
        )
        .order_by(HistoricalCandle.ts.desc())
        .limit(1)
    )
    r = (await db.execute(q)).first()
    return (r[0], bool(r[1])) if r else None


async def reference_price(
    db: AsyncSession, redis: Any, provider: str, instrument_id: int, now: datetime
) -> RefPrice | None:
    """The most recent of: the cached quote, the newest closed 1m and 1d candle of
    `provider` (ties go to the quote)."""
    best: RefPrice | None = None
    if redis is not None:
        q = await get_cached_quote(redis, instrument_id, now)
        if q is not None and q.ltp > 0:
            best = RefPrice(
                q.ltp, f"{q.provider_id}:quote", str(q.freshness), ensure_utc(q.ts), q.is_demo
            )
    cal = nse_calendar()
    for tf in (Timeframe.M1, Timeframe.D1):
        got = await _latest_candle(db, instrument_id, provider, tf)
        if got is None:
            continue
        bar, is_demo = got
        start = ensure_utc(bar.ts)
        if tf == Timeframe.M1:
            closed_at = min(start + timedelta(minutes=1), now)
        else:
            bounds = cal.session_bounds_utc(cal.local_date(start))
            closed_at = bounds[1] if bounds else start + timedelta(days=1)
            if closed_at > now:  # today's daily bar is not final yet
                continue
        if bar.close <= 0:
            continue
        if best is None or closed_at > best.ts:
            best = RefPrice(
                Decimal(bar.close),
                f"{provider}:candle_{tf.value}",
                str(Freshness.DEMO if is_demo else Freshness.HISTORICAL),
                closed_at,
                is_demo,
            )
    return best


def _warnings(data: RecordViewIn, ref: RefPrice) -> list[str]:
    w: list[str] = []
    inv = data.invalidation_price
    if inv is not None:
        if data.direction == "up" and inv >= ref.price:
            w.append("invalidation_price is not below the reference price for an 'up' view")
        if data.direction == "down" and inv <= ref.price:
            w.append("invalidation_price is not above the reference price for a 'down' view")
        if inv == ref.price:
            w.append("invalidation_price equals the reference price; no alert can fire")
    if ref.freshness not in (str(Freshness.LIVE), str(Freshness.DELAYED)):
        w.append(f"reference price is {ref.freshness} ({ref.source} at {ref.ts.isoformat()})")
    return w


async def record_view(
    db: AsyncSession,
    redis: Any,
    settings: Settings,
    data: RecordViewIn,
    *,
    now: datetime | None = None,
    commit: bool = True,
) -> RecordViewOut:
    now = ensure_utc(now or utcnow())
    ins = await get_by_symbol(db, data.exchange, data.symbol)
    if ins is None:
        raise ViewRefused("unknown_instrument", f"unknown instrument {data.exchange}:{data.symbol}")
    ref = await reference_price(
        db, redis, settings.default_market_data_provider, ins.instrument_id, now
    )
    if ref is None:
        raise ViewRefused(
            "no_reference_price",
            f"no quote or stored close for {data.symbol}; a view needs a reference price",
        )
    obs = AiObservation(
        ts=now,
        caller=data.caller,
        mode=data.mode,
        instrument_id=ins.instrument_id,
        direction=data.direction,
        horizon_days=data.horizon_days,
        confidence=data.confidence,
        invalidation=data.invalidation,
        invalidation_price=data.invalidation_price,
        statement=data.statement,
        ref_price=ref.price,
        ref_source=ref.source,
        ref_freshness=ref.freshness,
        ref_ts=ref.ts,
        tool_call_id=data.tool_call_id,
    )
    db.add(obs)
    await db.flush()
    out = RecordViewOut(
        observation_id=obs.id,
        ts=now,
        symbol=ins.symbol,
        instrument_id=ins.instrument_id,
        direction=data.direction,
        horizon_days=data.horizon_days,
        confidence=data.confidence,
        due_date=due_date(nse_calendar(), now, data.horizon_days),
        ref_price=ref.price,
        ref_source=ref.source,
        ref_freshness=ref.freshness,
        ref_ts=ref.ts,
        is_demo=ref.is_demo,
        invalidation=data.invalidation,
        invalidation_price=data.invalidation_price,
        warnings=_warnings(data, ref),
    )
    if commit:
        await db.commit()
    return out
