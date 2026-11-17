"""Build 1-minute candles from ticks and resample them. Pure in-memory logic, no I/O.

Rules (ADR-006): bar ``ts`` is the bar's open time in UTC, aligned to the exchange session
(first bar at session open, e.g. 09:15 IST; last bar one minute before close).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

from core.calendar import ExchangeCalendar
from core.models import Candle, Tick, Timeframe
from core.time import ensure_utc, floor_to

_MINUTE = timedelta(minutes=1)


@dataclass
class _OpenBar:
    ts: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int = 0
    oi: int | None = None
    provider_id: str = ""
    provider_ts: datetime | None = None
    received_at: datetime | None = None
    is_demo: bool = False
    trade_count: int = 0

    def to_candle(self, instrument_id: int) -> Candle:
        return Candle(
            instrument_id=instrument_id,
            timeframe=Timeframe.M1,
            ts=self.ts,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
            oi=self.oi,
            trade_count=self.trade_count,
            provider_id=self.provider_id,
            provider_ts=self.provider_ts,
            received_at=self.received_at or self.ts,
            is_demo=self.is_demo,
        )


@dataclass
class BuilderStats:
    ticks: int = 0
    late_ticks: int = 0  # older than the current bar by <= 1 bar; merged
    dropped_ticks: int = 0  # older than the current bar by > 1 bar; ignored
    outside_session: int = 0
    bars_emitted: int = 0


@dataclass
class _InstrumentState:
    bar: _OpenBar | None = None
    session_day: date | None = None
    last_cum_volume: int | None = None
    last_oi: int | None = None


class CandleBuilder:
    """Feed ticks, get closed 1-minute candles back.

    Volume: when ticks carry cumulative session ``volume`` the per-bar volume is the delta
    between successive ticks; when they only carry ``ltq`` the bar volume is the sum of ltq.
    """

    def __init__(self, calendar: ExchangeCalendar) -> None:
        self._cal = calendar
        self._state: dict[int, _InstrumentState] = defaultdict(_InstrumentState)
        self.stats = BuilderStats()

    # ------------------------------------------------------------------ public API
    def on_tick(self, tick: Tick) -> list[Candle]:
        self.stats.ticks += 1
        ts = ensure_utc(tick.ts)
        if not self._cal.is_open(ts):
            self.stats.outside_session += 1
            # A tick at/after close still closes the open bar for that instrument.
            return self._close_if_session_over(tick.instrument_id, ts)

        st = self._state[tick.instrument_id]
        day = self._cal.local_date(ts)
        emitted: list[Candle] = []
        if st.session_day != day:
            emitted.extend(self._flush_instrument(tick.instrument_id))
            st.session_day = day
            st.last_cum_volume = None
            st.last_oi = None

        bar_ts = floor_to(ts, 60)
        vol_delta = self._volume_delta(st, tick, bar_ts)
        if tick.oi is not None:
            st.last_oi = tick.oi

        bar = st.bar
        if bar is None or bar_ts > bar.ts:
            if bar is not None:
                emitted.append(bar.to_candle(tick.instrument_id))
                self.stats.bars_emitted += 1
            st.bar = self._new_bar(tick, bar_ts, vol_delta, st.last_oi)
            return emitted
        if bar_ts == bar.ts:
            self._update(bar, tick, vol_delta, st.last_oi)
            return emitted
        # late tick
        if bar.ts - bar_ts <= _MINUTE:
            self.stats.late_ticks += 1
            self._update(bar, tick, vol_delta, st.last_oi, late=True)
        else:
            self.stats.dropped_ticks += 1
        return emitted

    def on_time(self, now: datetime) -> list[Candle]:
        """Close bars whose minute has elapsed even if no further tick arrived."""
        now = ensure_utc(now)
        out: list[Candle] = []
        for iid, st in self._state.items():
            if st.bar is not None and st.bar.ts + _MINUTE <= now:
                out.append(st.bar.to_candle(iid))
                self.stats.bars_emitted += 1
                st.bar = None
        return out

    def flush(self) -> list[Candle]:
        """Force-close every open bar (session end, shutdown)."""
        out: list[Candle] = []
        for iid in list(self._state):
            out.extend(self._flush_instrument(iid))
        return out

    def open_bars(self) -> dict[int, Candle]:
        return {iid: st.bar.to_candle(iid) for iid, st in self._state.items() if st.bar}

    # ------------------------------------------------------------------ internals
    def _flush_instrument(self, iid: int) -> list[Candle]:
        st = self._state[iid]
        if st.bar is None:
            return []
        c = st.bar.to_candle(iid)
        st.bar = None
        self.stats.bars_emitted += 1
        return [c]

    def _close_if_session_over(self, iid: int, ts: datetime) -> list[Candle]:
        st = self._state.get(iid)
        if st is None or st.bar is None:
            return []
        bounds = self._cal.session_bounds_utc(self._cal.local_date(ts))
        if bounds is not None and ts >= bounds[1] and st.bar.ts < bounds[1]:
            return self._flush_instrument(iid)
        return []

    def _volume_delta(self, st: _InstrumentState, tick: Tick, bar_ts: datetime) -> int:
        if tick.volume is not None:
            if st.last_cum_volume is None:
                bounds = self._cal.session_bounds_utc(self._cal.local_date(bar_ts))
                first_bar = bounds is not None and bar_ts == bounds[0]
                delta = tick.volume if first_bar else 0
            else:
                delta = tick.volume - st.last_cum_volume
                if delta < 0:  # provider reset; trust the new counter
                    delta = tick.volume
            st.last_cum_volume = tick.volume
            return max(delta, 0)
        return tick.ltq or 0

    @staticmethod
    def _new_bar(tick: Tick, bar_ts: datetime, vol: int, oi: int | None) -> _OpenBar:
        return _OpenBar(
            ts=bar_ts,
            open=tick.ltp,
            high=tick.ltp,
            low=tick.ltp,
            close=tick.ltp,
            volume=vol,
            oi=oi,
            provider_id=tick.provider_id,
            provider_ts=tick.provider_ts,
            received_at=tick.received_at,
            is_demo=tick.is_demo,
            trade_count=1,
        )

    @staticmethod
    def _update(bar: _OpenBar, tick: Tick, vol: int, oi: int | None, late: bool = False) -> None:
        bar.high = max(bar.high, tick.ltp)
        bar.low = min(bar.low, tick.ltp)
        if not late:
            bar.close = tick.ltp
            bar.provider_ts = tick.provider_ts
            bar.received_at = tick.received_at
        bar.volume += vol
        bar.oi = oi
        bar.trade_count += 1


# ------------------------------------------------------------------------- resampling
_INTRADAY_MINUTES: dict[Timeframe, int] = {
    Timeframe.M5: 5,
    Timeframe.M15: 15,
    Timeframe.M30: 30,
    Timeframe.H1: 60,
}


@dataclass
class _Bucket:
    ts: datetime
    bars: list[Candle] = field(default_factory=list)


class Resampler:
    """Resample closed 1-minute candles to coarser timeframes, aligned to the session open."""

    def __init__(self, calendar: ExchangeCalendar) -> None:
        self._cal = calendar

    def resample(self, candles_1m: Iterable[Candle], timeframe: Timeframe) -> list[Candle]:
        if timeframe == Timeframe.M1:
            return sorted(candles_1m, key=lambda c: c.ts)
        if timeframe not in _INTRADAY_MINUTES and timeframe != Timeframe.D1:
            raise ValueError(f"unsupported resample target: {timeframe}")
        buckets: dict[tuple[int, datetime], _Bucket] = {}
        for c in sorted(candles_1m, key=lambda c: (c.instrument_id, c.ts)):
            if c.timeframe != Timeframe.M1:
                raise ValueError("resample expects 1-minute candles")
            key_ts = self._bucket_ts(c.ts, timeframe)
            b = buckets.setdefault((c.instrument_id, key_ts), _Bucket(ts=key_ts))
            b.bars.append(c)
        return [self._merge(b, timeframe) for b in buckets.values()]

    def _bucket_ts(self, ts: datetime, tf: Timeframe) -> datetime:
        day = self._cal.local_date(ts)
        bounds = self._cal.session_bounds_utc(day)
        session_open = bounds[0] if bounds else floor_to(ts, 86400)
        if tf == Timeframe.D1:
            return session_open
        n = _INTRADAY_MINUTES[tf]
        minutes = int((ts - session_open).total_seconds() // 60)
        idx = minutes // n if minutes >= 0 else -((-minutes + n - 1) // n)
        return session_open + timedelta(minutes=idx * n)

    @staticmethod
    def _merge(b: _Bucket, tf: Timeframe) -> Candle:
        bars = b.bars
        first, last = bars[0], bars[-1]
        return Candle(
            instrument_id=first.instrument_id,
            timeframe=tf,
            ts=b.ts,
            open=first.open,
            high=max(x.high for x in bars),
            low=min(x.low for x in bars),
            close=last.close,
            volume=sum(x.volume for x in bars),
            oi=last.oi,
            trade_count=sum(x.trade_count or 0 for x in bars) or None,
            derived_from=Timeframe.M1,
            provider_id=first.provider_id,
            provider_ts=last.provider_ts,
            received_at=max(x.received_at for x in bars),
            is_demo=any(x.is_demo for x in bars),
        )


def session_minutes(calendar: ExchangeCalendar, day: date) -> Sequence[datetime]:
    """Every expected 1-minute bar open time (UTC) for a session day; empty if closed."""
    bounds = calendar.session_bounds_utc(day)
    if bounds is None:
        return []
    o, c = bounds
    n = int((c - o).total_seconds() // 60)
    return [o + timedelta(minutes=i) for i in range(n)]


__all__ = [
    "BuilderStats",
    "CandleBuilder",
    "Resampler",
    "session_minutes",
]
