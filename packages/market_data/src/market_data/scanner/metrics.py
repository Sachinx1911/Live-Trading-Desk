"""Universe metrics for the scanner: one row per instrument from its daily bars (+ the
latest stored regime). Pure computation is in `metrics_for_instrument` so it can be unit
tested; `compute_universe_metrics` does the three bulk queries and loops."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import numpy as np
import polars as pl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import Contract, Exchange, HistoricalCandle, RegimeDaily
from core.db.models import Instrument as InstrumentRow
from core.db.models._enums import InstrumentType
from core.models import Timeframe
from core.time import IST, ensure_utc
from market_data.repo._lookup import provider_id
from market_data.repo.instruments import _TYPE_TO_SEGMENT
from strategy.indicators.library import ADX, ATR, EMA, RSI

MIN_BARS = 60
LOOKBACK_DAYS = 400
_SCAN_TYPES = (
    InstrumentType.EQUITY,
    InstrumentType.ETF,
    InstrumentType.INDEX,
    InstrumentType.FUTURE,
)


@dataclass(frozen=True)
class ScanInstrument:
    instrument_id: int
    symbol: str
    name: str
    segment: str
    lot_size: int
    underlying: str | None = None
    expiry: date | None = None


def _f(v: float) -> float | None:
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else round(float(v), 4)


def _pct(a: float, b: float) -> float | None:
    if b == 0 or math.isnan(a) or math.isnan(b):
        return None
    return round((a / b - 1.0) * 100.0, 4)


def metrics_for_instrument(
    ins: ScanInstrument,
    bars: pl.DataFrame,
    as_of: date,
    regime: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """`bars` has columns ts, open, high, low, close, volume, oi (floats), sorted ascending,
    daily. Returns None when there is not enough history."""
    n = bars.height
    if n < MIN_BARS:
        return None
    close = bars["close"].to_numpy().astype(float)
    high = bars["high"].to_numpy().astype(float)
    low = bars["low"].to_numpy().astype(float)
    opn = bars["open"].to_numpy().astype(float)
    vol = bars["volume"].to_numpy().astype(float)
    oi = bars["oi"].to_numpy().astype(float) if "oi" in bars.columns else np.full(n, np.nan)

    last, prev = close[-1], close[-2]
    ema20 = EMA().compute(bars, period=20)["value"][-1]
    ema50 = EMA().compute(bars, period=50)["value"][-1]
    ema200 = EMA().compute(bars, period=200)["value"][-1] if n >= 200 else float("nan")
    rsi14 = RSI().compute(bars, period=14)["value"][-1]
    atr14 = ATR().compute(bars, period=14)["value"][-1]
    adx14 = ADX().compute(bars, period=14)["value"][-1]
    win = min(n, 250)
    hi52, lo52 = float(np.max(high[-win:])), float(np.min(low[-win:]))
    avg20 = float(np.mean(vol[-21:-1])) if n > 21 else float("nan")
    rel = vol[-1] / avg20 if avg20 and not math.isnan(avg20) and avg20 > 0 else float("nan")

    if not math.isnan(ema200):
        if ema20 > ema50 > ema200:
            align = "bull"
        elif ema20 < ema50 < ema200:
            align = "bear"
        else:
            align = "mixed"
    else:
        align = "bull" if ema20 > ema50 else "bear" if ema20 < ema50 else "mixed"

    oi_chg = None
    if not math.isnan(oi[-1]) and n >= 2 and not math.isnan(oi[-2]) and oi[-2] > 0:
        oi_chg = _pct(oi[-1], oi[-2])
    reg = regime or {}
    return {
        "instrument_id": ins.instrument_id,
        "symbol": ins.symbol,
        "name": ins.name,
        "segment": ins.segment,
        "lot_size": ins.lot_size,
        "underlying": ins.underlying,
        "expiry": ins.expiry.isoformat() if ins.expiry else None,
        "sector": None,
        "last_close": _f(last),
        "prev_close": _f(prev),
        "change_1d_pct": _pct(last, prev),
        "change_5d_pct": _pct(last, close[-6]) if n > 6 else None,
        "change_20d_pct": _pct(last, close[-21]) if n > 21 else None,
        "gap_pct": _pct(opn[-1], prev),
        "volume": int(vol[-1]),
        "avg_volume_20": None if math.isnan(avg20) else int(avg20),
        "rel_volume": _f(rel),
        "atr14_pct": _f(atr14 / last * 100.0) if last else None,
        "rsi14": _f(rsi14),
        "adx14": _f(adx14),
        "ema20": _f(ema20),
        "ema50": _f(ema50),
        "ema200": _f(ema200),
        "ema_alignment": align,
        "dist_52w_high_pct": _pct(last, hi52),
        "dist_52w_low_pct": _pct(last, lo52),
        "oi": None
        if math.isnan(oi[-1]) or (ins.segment != "futures" and oi[-1] == 0)
        else int(oi[-1]),
        "oi_change_1d_pct": oi_chg,
        "regime_trend": reg.get("trend"),
        "regime_strength": reg.get("strength"),
        "regime_volatility": reg.get("volatility"),
        "regime_structure": reg.get("structure"),
        "bars": n,
        "as_of": as_of.isoformat(),
    }


def bars_frame(rows: list[tuple[Any, ...]]) -> pl.DataFrame:
    """rows: (ts, open, high, low, close, volume, oi) ascending."""
    return pl.DataFrame(
        {
            "ts": [r[0] for r in rows],
            "open": [float(r[1]) for r in rows],
            "high": [float(r[2]) for r in rows],
            "low": [float(r[3]) for r in rows],
            "close": [float(r[4]) for r in rows],
            "volume": [float(r[5] or 0) for r in rows],
            "oi": [float("nan") if r[6] is None else float(r[6]) for r in rows],
        }
    )


async def load_universe(session: AsyncSession, exchange: str = "NSE") -> list[ScanInstrument]:
    und = InstrumentRow.__table__.alias("und")
    q = (
        select(
            InstrumentRow.id,
            InstrumentRow.symbol,
            InstrumentRow.name,
            InstrumentRow.instrument_type,
            InstrumentRow.lot_size,
            Contract.expiry,
            und.c.symbol,
        )
        .join(Exchange, Exchange.id == InstrumentRow.exchange_id)
        .outerjoin(Contract, Contract.instrument_id == InstrumentRow.id)
        .outerjoin(und, und.c.id == Contract.underlying_id)
        .where(
            Exchange.code == exchange,
            InstrumentRow.instrument_type.in_(_SCAN_TYPES),
            InstrumentRow.is_tradable.is_(True),
        )
    )
    out = []
    for iid, sym, name, itype, lot, expiry, und_sym in (await session.execute(q)).all():
        out.append(
            ScanInstrument(iid, sym, name, _TYPE_TO_SEGMENT[itype].value, lot, und_sym, expiry)
        )
    return out


async def compute_universe_metrics(
    session: AsyncSession, *, provider: str, as_of_date: date, exchange: str = "NSE"
) -> list[dict[str, Any]]:
    pid = await provider_id(session, provider)
    universe = await load_universe(session, exchange)
    end = ensure_utc(
        datetime.combine(as_of_date + timedelta(days=1), datetime.min.time(), tzinfo=IST)
    )
    start = end - timedelta(days=LOOKBACK_DAYS)
    ids = [u.instrument_id for u in universe]
    by_ins: dict[int, list[tuple[Any, ...]]] = defaultdict(list)
    cq = (
        select(
            HistoricalCandle.instrument_id,
            HistoricalCandle.ts,
            HistoricalCandle.open,
            HistoricalCandle.high,
            HistoricalCandle.low,
            HistoricalCandle.close,
            HistoricalCandle.volume,
            HistoricalCandle.oi,
        )
        .where(
            HistoricalCandle.provider_id == pid,
            HistoricalCandle.timeframe == Timeframe.D1,
            HistoricalCandle.ts >= start,
            HistoricalCandle.ts < end,
            HistoricalCandle.instrument_id.in_(ids),
        )
        .order_by(HistoricalCandle.instrument_id, HistoricalCandle.ts)
    )
    for row in (await session.execute(cq)).all():
        by_ins[row[0]].append(tuple(row[1:]))
    rq = (
        select(RegimeDaily)
        .where(RegimeDaily.instrument_id.in_(ids), RegimeDaily.date <= as_of_date)
        .order_by(RegimeDaily.instrument_id, RegimeDaily.date.desc())
    )
    regimes: dict[int, dict[str, Any]] = {}
    for r in (await session.execute(rq)).scalars():
        regimes.setdefault(
            r.instrument_id,
            {
                "trend": r.trend.value,
                "strength": r.strength.value,
                "volatility": r.volatility.value,
                "structure": r.structure.value,
            },
        )
    rows: list[dict[str, Any]] = []
    for ins in universe:
        raw = by_ins.get(ins.instrument_id)
        if not raw or len(raw) < MIN_BARS:
            continue
        m = metrics_for_instrument(ins, bars_frame(raw), as_of_date, regimes.get(ins.instrument_id))
        if m:
            rows.append(m)
    rows.sort(key=lambda r: (r["segment"], r["symbol"]))
    return rows
