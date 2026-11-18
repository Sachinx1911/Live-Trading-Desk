"""Shared fixtures: synthetic candles and minimal DSL documents."""

from __future__ import annotations

import random
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from core.calendar import nse_calendar
from core.models import AssetClass, Candle, Instrument, Segment, Timeframe

CAL = nse_calendar()
TEST_INSTRUMENT = Instrument(
    instrument_id=1,
    exchange="NSE",
    segment=Segment.EQUITY,
    asset_class=AssetClass.STOCK,
    symbol="TEST",
    name="Test Equity",
    lot_size=1,
    tick_size=Decimal("0.05"),
)


def session_open_utc(d: date) -> datetime:
    bounds = CAL.session_bounds_utc(d)
    assert bounds is not None
    return bounds[0]


def trading_days(start: date, n: int) -> list[date]:
    out: list[date] = []
    d = start
    while len(out) < n:
        if CAL.is_trading_day(d):
            out.append(d)
        d += timedelta(days=1)
    return out


def make_candle(
    ts: datetime, o: float, h: float, lo: float, c: float, vol: int = 100, iid: int = 1
) -> Candle:
    return Candle(
        instrument_id=iid,
        timeframe=Timeframe.M1,
        ts=ts,
        open=Decimal(str(o)),
        high=Decimal(str(h)),
        low=Decimal(str(lo)),
        close=Decimal(str(c)),
        volume=vol,
        provider_id="import",
        received_at=ts,
    )


def linear_sessions(
    days: list[date], bars_per_session: int = 30, base: float = 100.0
) -> list[Candle]:
    """Deterministic: open = base + minute index within the session (+ 10 per day),
    high = open + 1, low = open - 1, close = open + 0.5."""
    out: list[Candle] = []
    for di, d in enumerate(days):
        start = session_open_utc(d)
        for i in range(bars_per_session):
            o = base + 10 * di + i
            out.append(make_candle(start + timedelta(minutes=i), o, o + 1, o - 1, o + 0.5))
    return out


def random_walk_sessions(
    days: list[date], seed: int = 7, start_px: float = 20000.0
) -> list[Candle]:
    rng = random.Random(seed)
    px = start_px
    out: list[Candle] = []
    for d in days:
        start = session_open_utc(d)
        for i in range(375):
            o = px
            drift = rng.gauss(0, 8)
            c = max(1.0, o + drift)
            hi = max(o, c) + abs(rng.gauss(0, 3))
            lo = min(o, c) - abs(rng.gauss(0, 3))
            out.append(
                make_candle(
                    start + timedelta(minutes=i),
                    round(o, 2),
                    round(hi, 2),
                    round(lo, 2),
                    round(c, 2),
                    vol=int(abs(rng.gauss(500, 100))),
                )
            )
            px = c
    return out


def minimal_dsl(**overrides: Any) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "dsl_schema_version": "1.0",
        "name": "always enter, time exit",
        "origin": "user_visual",
        "market": "NSE",
        "universe": {"kind": "instrument", "instrument_ids": ["1"]},
        "timeframe": "1m",
        "session": {
            "product": "INTRADAY",
            "trade_start": "09:16",
            "no_new_entries_after": "14:45",
            "square_off_at": "15:15",
        },
        "indicators": {},
        "direction": "long_only",
        "entry": {
            "long": {
                "kind": "compare",
                "left": {"kind": "price", "field": "close"},
                "op": "gt",
                "right": {"kind": "const", "value": 0},
            }
        },
        "exit": {"time_exit_bars": 2},
        "position_sizing": {"method": "fixed_quantity", "quantity": 10},
        "max_trades_per_day": 1,
    }
    doc.update(overrides)
    return doc


@pytest.fixture
def three_sessions() -> list[Candle]:
    return linear_sessions(trading_days(date(2026, 11, 16), 3))


@pytest.fixture
def instrument() -> Instrument:
    return TEST_INSTRUMENT


@pytest.fixture
def make_cfg() -> Callable[..., Any]:
    from backtest.config import BacktestConfig

    def _make(dsl: dict[str, Any], candles: list[Candle], **kw: Any) -> BacktestConfig:
        start = candles[0].ts
        end = candles[-1].ts + timedelta(days=1)
        base: dict[str, Any] = {
            "strategy_version_id": 1,
            "dsl": dsl,
            "instrument": TEST_INSTRUMENT,
            "start": start,
            "end": end,
            "seed": 42,
        }
        base.update(kw)
        return BacktestConfig(**base)

    return _make


UTC_ = UTC


@pytest.fixture
def candle_factory():  # type: ignore[no-untyped-def]
    """Expose make_candle as a fixture (importing `conftest` by name clashes across packages)."""
    return make_candle
