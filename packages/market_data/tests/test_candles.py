from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from core.calendar import nse_calendar
from core.models import Candle, Tick, Timeframe
from core.time import IST
from market_data.candles import CandleBuilder, Resampler, session_minutes

cal = nse_calendar()
DAY = date(2026, 11, 17)  # Tuesday


def ist(h: int, m: int, s: int = 0, d: date = DAY) -> datetime:
    return datetime(d.year, d.month, d.day, h, m, s, tzinfo=IST).astimezone(UTC)


def tick(iid: int, at: datetime, px: str, vol: int | None = None, ltq: int | None = None) -> Tick:
    return Tick(
        instrument_id=iid, ts=at, ltp=Decimal(px), ltq=ltq, volume=vol,
        provider_id="fake", provider_ts=at, received_at=at, is_demo=True,
    )  # fmt: skip


def test_bars_align_to_minute_and_emit_on_rollover() -> None:
    b = CandleBuilder(cal)
    assert b.on_tick(tick(1, ist(9, 15, 0), "100", vol=10)) == []
    assert b.on_tick(tick(1, ist(9, 15, 30), "101", vol=15)) == []
    assert b.on_tick(tick(1, ist(9, 15, 59), "99", vol=18)) == []
    out = b.on_tick(tick(1, ist(9, 16, 0), "100.5", vol=20))
    assert len(out) == 1
    c = out[0]
    assert c.ts == ist(9, 15) and c.timeframe == Timeframe.M1
    assert (c.open, c.high, c.low, c.close) == (
        Decimal(100),
        Decimal(101),
        Decimal(99),
        Decimal(99),
    )
    assert c.volume == 18  # first bar of session: cumulative volume counts from 0
    assert c.trade_count == 3 and c.is_demo and c.provider_id == "fake"
    nxt = b.open_bars()[1]
    assert nxt.ts == ist(9, 16) and nxt.volume == 2  # 20 - 18


def test_cumulative_volume_delta_vs_ltq_fallback() -> None:
    b = CandleBuilder(cal)
    b.on_tick(tick(1, ist(10, 0, 0), "10", vol=1000))  # not first bar: delta unknown -> 0
    b.on_tick(tick(1, ist(10, 0, 10), "10", vol=1030))
    b.on_tick(tick(1, ist(10, 0, 20), "10", vol=1020))  # provider reset -> trust new counter
    (c,) = b.on_tick(tick(1, ist(10, 1, 0), "10", vol=1025))
    assert c.volume == 30 + 1020
    b2 = CandleBuilder(cal)
    b2.on_tick(tick(2, ist(10, 0, 0), "10", ltq=5))
    b2.on_tick(tick(2, ist(10, 0, 5), "10", ltq=7))
    (c2,) = b2.on_tick(tick(2, ist(10, 1, 0), "10", ltq=1))
    assert c2.volume == 12


def test_late_and_dropped_ticks() -> None:
    b = CandleBuilder(cal)
    b.on_tick(tick(1, ist(11, 0, 0), "100"))
    b.on_tick(tick(1, ist(11, 1, 0), "101"))  # closes 11:00 bar
    b.on_tick(tick(1, ist(11, 0, 50), "150"))  # late by <= 1 bar: merged into high/low
    b.on_tick(tick(1, ist(10, 58, 0), "1"))  # late by > 1 bar: dropped
    bar = b.open_bars()[1]
    assert bar.high == Decimal(150) and bar.low == Decimal(101) and bar.close == Decimal(101)
    assert b.stats.late_ticks == 1 and b.stats.dropped_ticks == 1


def test_outside_session_ignored_and_session_close_flushes() -> None:
    b = CandleBuilder(cal)
    assert b.on_tick(tick(1, ist(9, 10, 0), "100")) == []
    assert b.stats.outside_session == 1
    b.on_tick(tick(1, ist(15, 29, 30), "100"))
    out = b.on_tick(tick(1, ist(15, 30, 0), "100"))  # at close: not a bar, but flushes
    assert [c.ts for c in out] == [ist(15, 29)]
    assert b.open_bars() == {}
    b.on_tick(tick(1, ist(9, 15, 0, date(2026, 11, 15)), "1"))  # Sunday
    assert b.stats.outside_session == 3


def test_flush_and_on_time_and_new_day_resets_volume() -> None:
    b = CandleBuilder(cal)
    b.on_tick(tick(1, ist(9, 15, 0), "100", vol=50))
    b.on_tick(tick(2, ist(9, 15, 0), "200", vol=5))
    assert b.on_time(ist(9, 15, 30)) == []
    closed = b.on_time(ist(9, 16, 0))
    assert sorted(c.instrument_id for c in closed) == [1, 2]
    b.on_tick(tick(1, ist(9, 17, 0), "100", vol=60))
    assert len(b.flush()) == 1
    nd = date(2026, 11, 18)
    b.on_tick(tick(1, ist(9, 15, 0, nd), "100", vol=7))
    assert b.open_bars()[1].volume == 7


def _minute_candles(iid: int, day: date, n: int) -> list[Candle]:
    out = []
    for i, ts in enumerate(session_minutes(cal, day)[:n]):
        px = Decimal(100 + i)
        out.append(
            Candle(
                instrument_id=iid,
                timeframe=Timeframe.M1,
                ts=ts,
                open=px,
                high=px + 1,
                low=px - 1,
                close=px + Decimal("0.5"),
                volume=10,
                trade_count=2,
                provider_id="fake",
                received_at=ts,
                is_demo=True,
            )
        )
    return out


def test_resample_5m_aligned_to_session_open() -> None:
    bars = _minute_candles(1, DAY, 12)
    out = Resampler(cal).resample(bars, Timeframe.M5)
    assert [c.ts for c in out] == [ist(9, 15), ist(9, 20), ist(9, 25)]
    first = out[0]
    assert first.open == Decimal(100) and first.close == Decimal("104.5")
    assert first.high == Decimal(105) and first.low == Decimal(99) and first.volume == 50
    assert first.derived_from == Timeframe.M1 and first.trade_count == 10
    assert out[-1].volume == 20  # partial last bucket (2 bars)


def test_resample_daily_and_errors() -> None:
    bars = _minute_candles(1, DAY, 375) + _minute_candles(1, date(2026, 11, 18), 5)
    out = Resampler(cal).resample(bars, Timeframe.D1)
    assert [c.ts for c in out] == [ist(9, 15), ist(9, 15, 0, date(2026, 11, 18))]
    assert out[0].volume == 3750 and out[0].close == bars[374].close
    with pytest.raises(ValueError):
        Resampler(cal).resample(bars, Timeframe.W1)
    with pytest.raises(ValueError):
        Resampler(cal).resample(out, Timeframe.M5)


def test_session_minutes_count() -> None:
    assert len(session_minutes(cal, DAY)) == 375
    assert session_minutes(cal, date(2026, 11, 15)) == []
    assert session_minutes(cal, DAY)[-1] == ist(15, 29)
