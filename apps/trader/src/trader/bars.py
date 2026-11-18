"""Incremental resampling of closed 1-minute candles into a strategy's primary timeframe,
session-aligned (first bar opens 09:15 IST). Emits a bar only when the next bucket starts
or on `flush()` at session close, so strategies see CLOSED bars only (ADR-002)."""

from __future__ import annotations

from datetime import datetime, timedelta

from core.calendar import ExchangeCalendar
from core.models import Candle, Timeframe


class BarAggregator:
    def __init__(self, timeframe: Timeframe, calendar: ExchangeCalendar) -> None:
        if timeframe.duration is None:
            raise ValueError("weekly/monthly timeframes are not supported in live paper trading")
        self.tf = timeframe
        self.cal = calendar
        self._open: Candle | None = None
        self._bucket: datetime | None = None

    def bucket_of(self, ts: datetime) -> datetime:
        local = ts.astimezone(self.cal.tz)
        bounds = self.cal.session_bounds_utc(local.date())
        if bounds is None:
            # Not a session day (should not happen for collector candles); minute floor.
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

    def bucket_end(self) -> datetime | None:
        if self._bucket is None:
            return None
        if self.tf == Timeframe.D1:
            bounds = self.cal.session_bounds_utc(self._bucket.astimezone(self.cal.tz).date())
            return bounds[1] if bounds else None
        dur = self.tf.duration
        assert dur is not None
        return self._bucket + dur

    def maybe_close(self, now: datetime) -> Candle | None:
        """Close the open bucket if the clock passed its end + a small grace (late 1m bar)."""
        end = self.bucket_end()
        if end is not None and now >= end + timedelta(seconds=20):
            return self.flush()
        return None
