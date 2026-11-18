"""Historical feed: validated, time-ordered market events for the runner.

No look-ahead by construction: a bar is handed to the engine only when the simulated clock
reaches that bar's close, and the fill quote for `next_bar_open` carries the NEXT bar's open
one second after the bar opens (so a market order created at the previous close fills on it).
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal

from core.calendar import ExchangeCalendar
from core.models import Candle, Freshness, Quote, Timeframe
from core.time import ensure_utc

EventKind = Literal["bar", "open", "close", "session_end"]


class DataOrderError(ValueError):
    pass


@dataclass(frozen=True)
class MarketEvent:
    kind: EventKind
    ts: datetime
    candle: Candle | None = None
    quote: Quote | None = None
    session_date: datetime | None = None  # local date (midnight, tz-aware) for session_end


class BarAggregator:
    """Session-aligned resampling of closed 1m bars (identical semantics to the paper runner)."""

    def __init__(self, timeframe: Timeframe, calendar: ExchangeCalendar) -> None:
        if timeframe.duration is None:
            raise ValueError("weekly/monthly timeframes are not supported")
        self.tf = timeframe
        self.cal = calendar
        self._open: Candle | None = None
        self._bucket: datetime | None = None

    def bucket_of(self, ts: datetime) -> datetime:
        local = ts.astimezone(self.cal.tz)
        bounds = self.cal.session_bounds_utc(local.date())
        if bounds is None:
            return ts.replace(second=0, microsecond=0)
        start, _ = bounds
        if self.tf == Timeframe.D1:
            return start
        dur = self.tf.duration
        assert dur is not None
        n = int((ts - start).total_seconds() // dur.total_seconds())
        return start + n * dur

    def on_1m(self, c: Candle) -> Candle | None:
        if self.tf == Timeframe.M1:
            return c
        b = self.bucket_of(c.ts)
        closed: Candle | None = None
        if self._open is not None and self._bucket != b:
            closed = self._open
            self._open = None
        if self._open is None:
            self._bucket = b
            self._open = c.model_copy(
                update={"ts": b, "timeframe": self.tf, "derived_from": Timeframe.M1}
            )
        else:
            o = self._open
            self._open = o.model_copy(
                update={
                    "high": max(o.high, c.high),
                    "low": min(o.low, c.low),
                    "close": c.close,
                    "volume": o.volume + c.volume,
                    "oi": c.oi if c.oi is not None else o.oi,
                    "received_at": c.received_at,
                    "provider_ts": c.provider_ts,
                }
            )
        return closed

    def flush(self) -> Candle | None:
        c, self._open, self._bucket = self._open, None, None
        return c


def bar_close_time(c: Candle, calendar: ExchangeCalendar) -> datetime:
    ts = ensure_utc(c.ts)
    if c.timeframe == Timeframe.D1 or c.timeframe.duration is None:
        bounds = calendar.session_bounds_utc(ts.astimezone(calendar.tz).date())
        return bounds[1] if bounds else ts + timedelta(days=1)
    return ts + c.timeframe.duration


def data_hash(candles: Sequence[Candle]) -> str:
    h = hashlib.sha256()
    for c in candles:
        h.update(f"{ensure_utc(c.ts).isoformat()}|{c.close}".encode())
    return h.hexdigest()


class HistoricalFeed:
    """Build from 1-minute bars (or bars already at the target timeframe, or daily bars)."""

    def __init__(
        self,
        candles: Sequence[Candle],
        timeframe: Timeframe,
        calendar: ExchangeCalendar,
        *,
        tick_size: Decimal = Decimal("0.05"),
        start: datetime | None = None,
        end: datetime | None = None,
        fill_mode: str = "next_bar_open",
    ) -> None:
        self.tf = timeframe
        self.cal = calendar
        self.tick = tick_size
        self.fill_mode = fill_mode
        raw = self._validate(candles)
        if start is not None:
            s = ensure_utc(start)
            raw = [c for c in raw if ensure_utc(c.ts) >= s]
        if end is not None:
            e = ensure_utc(end)
            raw = [c for c in raw if ensure_utc(c.ts) < e]
        self.source_hash = data_hash(raw)
        self.bars = self._resample(raw)
        if timeframe == Timeframe.D1:
            self.bars = [
                b for b in self.bars if self.cal.is_trading_day(b.ts.astimezone(self.cal.tz).date())
            ]

    # ------------------------------------------------------------------ validation
    @staticmethod
    def _validate(candles: Sequence[Candle]) -> list[Candle]:
        out: list[Candle] = []
        last: datetime | None = None
        for c in candles:
            ts = ensure_utc(c.ts)
            if last is not None:
                if ts < last:
                    raise DataOrderError(
                        f"candles out of order at {ts.isoformat()} (prev {last.isoformat()})"
                    )
                if ts == last:
                    continue  # duplicate timestamp: keep the first
            out.append(c)
            last = ts
        return out

    def _resample(self, raw: list[Candle]) -> list[Candle]:
        if not raw:
            return []
        src_tf = raw[0].timeframe
        if src_tf == self.tf:
            return list(raw)
        if src_tf != Timeframe.M1:
            raise ValueError(f"feed needs 1m or {self.tf.value} bars, got {src_tf.value}")
        agg = BarAggregator(self.tf, self.cal)
        out: list[Candle] = []
        current_day = None
        for c in raw:
            day = ensure_utc(c.ts).astimezone(self.cal.tz).date()
            if current_day is not None and day != current_day:
                tail = agg.flush()
                if tail is not None:
                    out.append(tail)
            current_day = day
            closed = agg.on_1m(c)
            if closed is not None:
                out.append(closed)
        tail = agg.flush()
        if tail is not None:
            out.append(tail)
        return out

    # ------------------------------------------------------------------ events
    def _quote(self, c: Candle, price: Decimal, ts: datetime) -> Quote:
        # No bid/ask on purpose: the simulator then applies the configured slippage model
        # to this reference price (bid/ask present would mean "fill at the book, no slippage").
        return Quote(
            instrument_id=c.instrument_id,
            ts=ts,
            ltp=price,
            volume=c.volume,
            oi=c.oi,
            provider_id=c.provider_id,
            provider_ts=ts,
            received_at=ts,
            is_demo=c.is_demo,
            freshness=Freshness.HISTORICAL,
        )

    def events(self) -> Iterator[MarketEvent]:
        """Strictly non-decreasing ts. Per bar: ("bar", candle) at its close, then the fill
        quote for the next bar ("open" at next.ts + 1 s) or ("close" at close + 1 s) in
        bar_close mode; ("session_end") after the last bar of each session."""
        bars = self.bars
        n = len(bars)
        for i, c in enumerate(bars):
            close_ts = bar_close_time(c, self.cal)
            yield MarketEvent("bar", close_ts, candle=c)
            nxt = bars[i + 1] if i + 1 < n else None
            same_session = (
                nxt is not None
                and ensure_utc(nxt.ts).astimezone(self.cal.tz).date()
                == close_ts.astimezone(self.cal.tz).date()
            )
            if self.fill_mode == "bar_close":
                yield MarketEvent(
                    "close",
                    close_ts + timedelta(seconds=1),
                    quote=self._quote(c, c.close, close_ts + timedelta(seconds=1)),
                )
            if nxt is not None and same_session:
                if self.fill_mode == "next_bar_open":
                    ots = ensure_utc(nxt.ts) + timedelta(seconds=1)
                    yield MarketEvent("open", ots, quote=self._quote(nxt, nxt.open, ots))
            else:
                local_mid = close_ts.astimezone(self.cal.tz).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                yield MarketEvent("session_end", close_ts, candle=c, session_date=local_mid)

    def __len__(self) -> int:
        return len(self.bars)
