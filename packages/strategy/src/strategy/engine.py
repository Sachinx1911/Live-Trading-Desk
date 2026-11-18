"""The single strategy engine (ADR-002). Pure and deterministic: feed closed candles, get
signals. Backtest, replay, paper and live all drive this same class.

Semantics (spec §11): rules run once per closed primary bar; entries pass session window →
regime filters → time filters → position/trade caps → cooldown → condition (confirm_bars);
stops/targets are priced at entry and handed to the execution layer; trailing stops are
recomputed per bar and never loosen; square-off is unconditional at the configured time.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Literal

import polars as pl

from core.calendar import ExchangeCalendar
from core.models import Candle, OrderSide, Signal
from core.time import ensure_utc
from strategy.dsl.schema import (
    ArithRef,
    Between,
    Compare,
    Condition,
    ConstRef,
    Cross,
    Group,
    IndicatorRef,
    Label,
    LevelSpec,
    Not,
    Operand,
    PriceRef,
    Slope,
    StrategyDocument,
    TargetSpec,
    Timeframe,
)
from strategy.indicators import IndicatorError
from strategy.indicators import get as get_indicator

RegimeProvider = Callable[[datetime], dict[str, Any]]

_TF_MINUTES: dict[str, int] = {"1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30, "1h": 60}
_PRICE_COLS = ("open", "high", "low", "close", "volume", "oi")
SESSION_OPEN_MIN = 9 * 60 + 15


def _hhmm(value: str | None) -> time | None:
    if value is None:
        return None
    h, m = value.split(":")
    return time(int(h), int(m))


def _q(x: float) -> Decimal:
    return Decimal(str(round(x, 2)))


@dataclass
class EngineState:
    position: Literal["flat", "long", "short"] = "flat"
    quantity: int = 0
    avg_price: Decimal | None = None
    entry_bar: int | None = None
    bars_in_trade: int = 0
    stop_price: Decimal | None = None
    target_price: Decimal | None = None
    trailing_active: bool = False
    trades_today: int = 0
    session_date: date | None = None
    last_exit_bar: int | None = None
    last_signal: Signal | None = None
    squared_off_today: bool = False
    confirm_count_long: int = 0
    confirm_count_short: int = 0
    bar_index: int = -1
    warmed_up: bool = False
    rejections: list[str] = field(default_factory=list)


class StrategyEngine:
    def __init__(
        self,
        doc: StrategyDocument,
        instrument_id: int,
        calendar: ExchangeCalendar,
        strategy_version_id: int,
        regime_provider: RegimeProvider | None = None,
        *,
        monitor_levels: bool = True,
        max_rows: int = 800,
    ) -> None:
        self.doc = doc
        self.instrument_id = instrument_id
        self.cal = calendar
        self.tz = calendar.tz
        self.version_id = strategy_version_id
        self.regime_provider = regime_provider
        self.monitor_levels = monitor_levels
        self._rows: list[dict[str, Any]] = []
        self._max_rows = max_rows
        self._ind_cols: dict[str, pl.DataFrame] = {}  # indicator id -> outputs, primary-aligned
        self._ctx_cols: dict[str, pl.DataFrame] = {}
        self.state = EngineState()
        self.warmup_bars = self._compute_warmup()
        self._validate_timeframes()

    # ------------------------------------------------------------------ setup
    def _compute_warmup(self) -> int:
        w = 1
        for spec in self.doc.indicators.values():
            if spec.timeframe is None or spec.timeframe == self.doc.timeframe:
                w = max(w, get_indicator(spec.type).warmup(spec.params))
            else:
                mult = self._ctx_multiple(spec.timeframe)
                w = max(w, get_indicator(spec.type).warmup(spec.params) * mult)
        return w

    def _ctx_multiple(self, tf: Timeframe) -> int:
        p, c = _TF_MINUTES.get(self.doc.timeframe), _TF_MINUTES.get(tf)
        if p is None or c is None or c % p != 0:
            raise IndicatorError(
                f"context timeframe {tf} must be an intraday multiple of {self.doc.timeframe}"
            )
        return c // p

    def _validate_timeframes(self) -> None:
        for tf in self.doc.context_timeframes:
            self._ctx_multiple(tf)

    # ------------------------------------------------------------------ position
    def set_position(self, qty: int, avg_price: Decimal | None) -> None:
        """Runner reports the real position after fills. The engine never assumes."""
        st = self.state
        if qty == 0:
            if st.position != "flat":
                st.last_exit_bar = st.bar_index
            st.position = "flat"
            st.quantity = 0
            st.avg_price = None
            st.entry_bar = None
            st.bars_in_trade = 0
            st.stop_price = None
            st.target_price = None
            st.trailing_active = False
            return
        new_pos: Literal["long", "short"] = "long" if qty > 0 else "short"
        if st.position != new_pos:
            st.entry_bar = st.bar_index
            st.bars_in_trade = 0
            st.trades_today += 1
        st.position = new_pos
        st.quantity = abs(qty)
        st.avg_price = avg_price
        if st.stop_price is None and st.last_signal is not None and st.last_signal.kind == "entry":
            st.stop_price = st.last_signal.stop_price
            st.target_price = st.last_signal.target_price

    # ------------------------------------------------------------------ data
    def _append(self, c: Candle) -> None:
        self._rows.append(
            {
                "ts": ensure_utc(c.ts),
                "open": float(c.open),
                "high": float(c.high),
                "low": float(c.low),
                "close": float(c.close),
                "volume": float(c.volume),
                "oi": float(c.oi) if c.oi is not None else None,
            }
        )
        if len(self._rows) > self._max_rows:
            self._rows = self._rows[-self._max_rows :]

    def _frame(self) -> pl.DataFrame:
        return pl.DataFrame(
            self._rows,
            schema={
                "ts": pl.Datetime("us", "UTC"),
                "open": pl.Float64,
                "high": pl.Float64,
                "low": pl.Float64,
                "close": pl.Float64,
                "volume": pl.Float64,
                "oi": pl.Float64,
            },
        )

    def _resample(self, df: pl.DataFrame, tf: Timeframe) -> pl.DataFrame:
        """Session-aligned resample of primary bars into a context timeframe (closed bars only)."""
        mins = _TF_MINUTES[tf]
        local = df["ts"].dt.convert_time_zone(str(self.tz))
        d = df.with_columns(
            local.dt.date().alias("_d"),
            (((local.dt.hour() * 60 + local.dt.minute()) - SESSION_OPEN_MIN) // mins).alias("_b"),
        )
        agg = d.group_by(["_d", "_b"], maintain_order=True).agg(
            pl.col("ts").first(),
            pl.col("open").first(),
            pl.col("high").max(),
            pl.col("low").min(),
            pl.col("close").last(),
            pl.col("volume").sum(),
            pl.col("oi").last(),
            pl.len().alias("_n"),
        )
        # the last bucket is only closed when it contains a full set of primary bars
        full = _TF_MINUTES[tf] // _TF_MINUTES[self.doc.timeframe]
        if agg.height and agg["_n"][-1] < full:
            agg = agg.head(agg.height - 1)
        return agg.drop(["_d", "_b", "_n"])

    def _recompute(self) -> None:
        df = self._frame()
        ctx_frames: dict[str, pl.DataFrame] = {}
        for iid, spec in self.doc.indicators.items():
            ind = get_indicator(spec.type)
            params = dict(spec.params)
            if spec.type in ("EMA", "SMA", "RSI", "BOLLINGER", "MACD"):
                params.setdefault("source", spec.source)
            if spec.timeframe is None or spec.timeframe == self.doc.timeframe:
                self._ind_cols[iid] = ind.compute(df, **params)
            else:
                if spec.timeframe not in ctx_frames:
                    ctx_frames[spec.timeframe] = self._resample(df, spec.timeframe)
                self._ctx_cols[iid] = ind.compute(ctx_frames[spec.timeframe], **params)

    # ------------------------------------------------------------------ operands
    def _value(self, op: Operand, offset_base: int = 0) -> float | str | None:
        if isinstance(op, ConstRef):
            return op.value
        if isinstance(op, PriceRef):
            idx = len(self._rows) - 1 - op.offset - offset_base
            if idx < 0:
                return None
            v = self._rows[idx][op.field]
            return None if v is None else float(v)
        if isinstance(op, IndicatorRef):
            return self._ind_value(op.id, op.field, op.offset + offset_base)
        if isinstance(op, ArithRef):
            left, right = self._value(op.left, offset_base), self._value(op.right, offset_base)
            if not isinstance(left, int | float) or not isinstance(right, int | float):
                return None
            if op.op == "+":
                return left + right
            if op.op == "-":
                return left - right
            if op.op == "*":
                return left * right
            return None if right == 0 else left / right
        return None

    def _ind_value(self, iid: str, field_: str, offset: int) -> float | str | None:
        cols = self._ind_cols.get(iid)
        if cols is None:
            cols = self._ctx_cols.get(iid)
        if cols is None or cols.height == 0:
            return None
        idx = cols.height - 1 - offset
        if idx < 0:
            return None
        v = cols[field_][idx]
        if v is None:
            return None
        if isinstance(v, str):
            return v
        f = float(v)
        return None if math.isnan(f) else f

    # ------------------------------------------------------------------ conditions
    def _eval(self, c: Condition, base: int = 0) -> bool:
        if isinstance(c, Group):
            results = (self._eval(x, base) for x in c.conditions)
            return all(results) if c.op == "and" else any(results)
        if isinstance(c, Not):
            return not self._eval(c.condition, base)
        if isinstance(c, Compare):
            left, right = self._value(c.left, base), self._value(c.right, base)
            if not isinstance(left, int | float) or not isinstance(right, int | float):
                return False
            return {
                "gt": left > right,
                "gte": left >= right,
                "lt": left < right,
                "lte": left <= right,
                "eq": math.isclose(left, right, rel_tol=1e-9),
            }[c.op]
        if isinstance(c, Cross):
            l0, r0 = self._value(c.left, base), self._value(c.right, base)
            l1, r1 = self._value(c.left, base + 1), self._value(c.right, base + 1)
            if not all(isinstance(x, int | float) for x in (l0, r0, l1, r1)):
                return False
            assert isinstance(l0, int | float) and isinstance(r0, int | float)
            assert isinstance(l1, int | float) and isinstance(r1, int | float)
            if c.direction == "crosses_above":
                return l1 <= r1 and l0 > r0
            return l1 >= r1 and l0 < r0
        if isinstance(c, Between):
            v, lo, hi = (
                self._value(c.value, base),
                self._value(c.low, base),
                self._value(c.high, base),
            )
            if not all(isinstance(x, int | float) for x in (v, lo, hi)):
                return False
            assert isinstance(v, int | float) and isinstance(lo, int | float)
            assert isinstance(hi, int | float)
            return lo <= v <= hi
        if isinstance(c, Slope):
            now, then = self._value(c.value, base), self._value(c.value, base + c.bars)
            if not isinstance(now, int | float) or not isinstance(then, int | float):
                return False
            if c.strict:
                vals = [self._value(c.value, base + i) for i in range(c.bars + 1)]
                if not all(isinstance(x, int | float) for x in vals):
                    return False
                seq = [float(x) for x in vals if isinstance(x, int | float)]  # newest first
                steps = [seq[i] - seq[i + 1] for i in range(len(seq) - 1)]
                return (
                    all(s > 0 for s in steps)
                    if c.direction == "rising"
                    else all(s < 0 for s in steps)
                )
            return now > then if c.direction == "rising" else now < then
        if isinstance(c, Label):
            v = self._value(c.value, base)
            if v is None:
                return False
            if isinstance(c.equals, str):
                return str(v) == c.equals
            return isinstance(v, int | float) and math.isclose(float(v), c.equals)
        return False

    # ------------------------------------------------------------------ gates
    def _local(self, ts: datetime) -> datetime:
        return ensure_utc(ts).astimezone(self.tz)

    def _bar_close(self, ts: datetime) -> datetime:
        mins = _TF_MINUTES.get(self.doc.timeframe)
        return ts + timedelta(minutes=mins) if mins else ts

    def _entry_window_ok(self, ts: datetime, reasons: list[str]) -> bool:
        s = self.doc.session
        local = self._local(self._bar_close(ts))
        t = local.time()
        if local.weekday() not in s.allowed_weekdays:
            reasons.append("weekday not allowed")
            return False
        start = _hhmm(s.trade_start) or time(9, 15)
        if s.skip_first_minutes:
            mins = SESSION_OPEN_MIN + s.skip_first_minutes
            start = max(start, time(mins // 60, mins % 60))
        cutoff = _hhmm(s.no_new_entries_after) or _hhmm(s.square_off_at) or time(15, 30)
        if not (start <= t < cutoff):
            reasons.append("outside entry window")
            return False
        for tf in self.doc.time_filters:
            a, b = _hhmm(tf.start), _hhmm(tf.end)
            if a is None or b is None:
                continue
            inside = a <= t < b
            if tf.mode == "block_entries" and inside:
                reasons.append(f"blocked by time filter {tf.start}-{tf.end}")
                return False
            if tf.mode == "allow_entries" and not inside:
                reasons.append(f"outside allowed window {tf.start}-{tf.end}")
                return False
        return True

    def _regime_ok(self, ts: datetime, reasons: list[str]) -> bool:
        if not self.doc.regime_filters:
            return True
        ctx = self.regime_provider(ts) if self.regime_provider else {}
        for rf in self.doc.regime_filters:
            if rf.source == "adx":
                v = self._ind_value(rf.indicator_id or "", "value", 0)
                if not isinstance(v, int | float):
                    reasons.append("adx not available")
                    return False
                if rf.min is not None and v < rf.min:
                    reasons.append(f"adx {v:.1f} < {rf.min}")
                    return False
                if rf.max is not None and v > rf.max:
                    reasons.append(f"adx {v:.1f} > {rf.max}")
                    return False
            elif rf.source == "vix":
                vix = ctx.get("vix")
                if not isinstance(vix, int | float):
                    reasons.append("vix not available")
                    return False
                if (rf.min is not None and vix < rf.min) or (rf.max is not None and vix > rf.max):
                    reasons.append(f"vix {vix} outside [{rf.min}, {rf.max}]")
                    return False
            elif rf.source in ("daily_trend", "regime_label"):
                label = ctx.get("daily_trend" if rf.source == "daily_trend" else "regime_label")
                if rf.allowed and label not in rf.allowed:
                    reasons.append(f"{rf.source}={label} not in {rf.allowed}")
                    return False
        return True

    # ------------------------------------------------------------------ levels
    def _atr(self, iid: str | None) -> float | None:
        v = self._ind_value(iid or "", "value", 0)
        return v if isinstance(v, int | float) else None

    def _level_distance(
        self, spec: LevelSpec, entry: float, side: Literal["long", "short"]
    ) -> float | None:
        """Absolute price level for a stop/target spec; None when not computable yet."""
        sign = -1.0 if side == "long" else 1.0  # stop direction for a long is below
        if spec.unit == "points" and spec.value is not None:
            return entry + sign * spec.value
        if spec.unit == "percent" and spec.value is not None:
            return entry * (1 + sign * spec.value / 100)
        if spec.unit == "atr" and spec.value is not None:
            atr = self._atr(spec.atr_indicator_id)
            return None if atr is None else entry + sign * spec.value * atr
        if spec.unit == "structure" and spec.structure is not None:
            field_ = {
                "swing_low": "last_low",
                "swing_high": "last_high",
                "prev_day_low": "low",
                "prev_day_high": "high",
                "opening_range_low": "low",
                "opening_range_high": "high",
            }[spec.structure]
            iid = spec.structure_indicator_id or self._find_structure_indicator(spec.structure)
            v = self._ind_value(iid or "", field_, 0) if iid else None
            if not isinstance(v, int | float):
                return None
            return v + sign * spec.buffer_points
        if spec.unit == "indicator" and spec.indicator_ref is not None:
            v = self._value(spec.indicator_ref)
            return v if isinstance(v, int | float) else None
        return None

    def _find_structure_indicator(self, structure: str) -> str | None:
        want = (
            "SWING"
            if structure.startswith("swing")
            else ("PREV_DAY" if structure.startswith("prev_day") else "OPENING_RANGE")
        )
        for iid, spec in self.doc.indicators.items():
            if spec.type == want:
                return iid
        return None

    def _stop_target(
        self, entry: float, side: Literal["long", "short"]
    ) -> tuple[Decimal | None, Decimal | None]:
        stop = self._level_distance(self.doc.stop_loss, entry, side) if self.doc.stop_loss else None
        target: float | None = None
        tgt: TargetSpec | None = self.doc.target
        if tgt is not None:
            if tgt.rr_multiple is not None and stop is not None:
                dist = abs(entry - stop) * tgt.rr_multiple
                target = entry + dist if side == "long" else entry - dist
            elif tgt.unit is not None:
                # target is on the profit side: flip the direction used for stops
                flip: Literal["long", "short"] = "short" if side == "long" else "long"
                target = self._level_distance(tgt, entry, flip)
        return (_q(stop) if stop is not None else None, _q(target) if target is not None else None)

    def _trail(self, close: float, side: Literal["long", "short"]) -> Decimal | None:
        tr = self.doc.trailing
        st = self.state
        if tr is None or st.avg_price is None:
            return None
        entry = float(st.avg_price)
        profit = close - entry if side == "long" else entry - close
        if not st.trailing_active and tr.activate_after is not None:
            lvl = self._level_distance(
                tr.activate_after, entry, "short" if side == "long" else "long"
            )
            if lvl is None or (side == "long" and close < lvl) or (side == "short" and close > lvl):
                return None
            st.trailing_active = True
        if profit <= 0 and tr.activate_after is None:
            return None
        sign = -1.0 if side == "long" else 1.0
        new: float | None = None
        if tr.mode == "atr" and tr.value is not None:
            atr = self._atr(tr.atr_indicator_id)
            new = None if atr is None else close + sign * tr.value * atr
        elif tr.mode == "percent" and tr.value is not None:
            new = close * (1 + sign * tr.value / 100)
        elif tr.mode == "points" and tr.value is not None:
            new = close + sign * tr.value
        elif tr.mode == "indicator" and tr.indicator_ref is not None:
            v = self._value(tr.indicator_ref)
            new = v if isinstance(v, int | float) else None
        elif tr.mode == "swing":
            iid = self._find_structure_indicator("swing_low")
            v = self._ind_value(iid or "", "last_low" if side == "long" else "last_high", 0)
            new = v if isinstance(v, int | float) else None
        if new is None:
            return None
        cur = float(st.stop_price) if st.stop_price is not None else None
        tighter = cur is None or (side == "long" and new > cur) or (side == "short" and new < cur)
        return _q(new) if tighter else None

    # ------------------------------------------------------------------ signals
    def _signal(
        self,
        ts: datetime,
        side: OrderSide,
        kind: str,
        reason: str,
        price: float,
        *,
        stop: Decimal | None = None,
        target: Decimal | None = None,
        qty: int | None = None,
    ) -> Signal:
        sig = Signal(
            strategy_version_id=self.version_id,
            instrument_id=self.instrument_id,
            ts=ts,
            side=side,
            kind=kind,
            reason=reason,
            reference_price=_q(price),
            stop_price=stop,
            target_price=target,
            suggested_quantity=qty,
        )
        self.state.last_signal = sig
        return sig

    def _suggested_qty(self) -> int | None:
        ps = self.doc.position_sizing
        if ps is None:
            return None
        if ps.method == "fixed_quantity":
            return ps.quantity
        if ps.method == "fixed_lots":
            return ps.lots  # lots; the runner multiplies by lot size
        return None

    def _roll_session(self, ts: datetime) -> None:
        d = self._local(ts).date()
        st = self.state
        if st.session_date != d:
            st.session_date = d
            st.trades_today = 0
            st.squared_off_today = False
            st.confirm_count_long = 0
            st.confirm_count_short = 0

    # ------------------------------------------------------------------ public
    def on_candle(self, candle: Candle) -> list[Signal]:
        if candle.instrument_id != self.instrument_id:
            return []
        ts = ensure_utc(candle.ts)
        self._roll_session(ts)
        self._append(candle)
        st = self.state
        st.bar_index += 1
        st.rejections = []
        if len(self._rows) < self.warmup_bars:
            st.warmed_up = False
            return []
        st.warmed_up = True
        self._recompute()
        if st.position != "flat":
            st.bars_in_trade += 1
        close = float(candle.close)
        out: list[Signal] = []

        # ---- open position: exits, levels, trailing --------------------------------
        if st.position != "flat":
            side: Literal["long", "short"] = st.position
            exit_side = OrderSide.SELL if side == "long" else OrderSide.BUY
            ex = self.doc.exit
            reason: str | None = None
            if self.monitor_levels:
                hi, lo = float(candle.high), float(candle.low)
                if st.stop_price is not None and (
                    (side == "long" and lo <= float(st.stop_price))
                    or (side == "short" and hi >= float(st.stop_price))
                ):
                    out.append(
                        self._signal(ts, exit_side, "stop", "stop loss hit", float(st.stop_price))
                    )
                    return out
                if st.target_price is not None and (
                    (side == "long" and hi >= float(st.target_price))
                    or (side == "short" and lo <= float(st.target_price))
                ):
                    out.append(
                        self._signal(ts, exit_side, "target", "target hit", float(st.target_price))
                    )
                    return out
            if ex is not None:
                rule = ex.long if side == "long" else ex.short
                if rule is not None and self._eval(rule):
                    reason = f"exit.{side} rule"
                elif ex.time_exit_bars is not None and st.bars_in_trade >= ex.time_exit_bars:
                    reason = f"time exit after {ex.time_exit_bars} bars"
                elif ex.exit_on_opposite_signal and self.doc.entry is not None:
                    opp = self.doc.entry.short if side == "long" else self.doc.entry.long
                    if opp is not None and self._eval(opp):
                        reason = "opposite entry signal"
            if reason is not None:
                out.append(self._signal(ts, exit_side, "exit", reason, close))
                return out
            new_stop = self._trail(close, side)
            if new_stop is not None:
                st.stop_price = new_stop
                out.append(
                    self._signal(
                        ts, exit_side, "stop", "trailing stop tightened", close, stop=new_stop
                    )
                )
            return out

        # ---- flat: entries -----------------------------------------------------------
        entry = self.doc.entry
        if entry is None:
            return out
        reasons = st.rejections
        if not self._entry_window_ok(ts, reasons) or not self._regime_ok(ts, reasons):
            st.confirm_count_long = st.confirm_count_short = 0
            return out
        if (
            self.doc.max_trades_per_day is not None
            and st.trades_today >= self.doc.max_trades_per_day
        ):
            reasons.append("max_trades_per_day reached")
            return out
        if st.last_exit_bar is not None and st.bar_index - st.last_exit_bar <= entry.cooldown_bars:
            reasons.append("cooldown")
            return out
        want_long = self.doc.direction in ("long_only", "both") and entry.long is not None
        want_short = self.doc.direction in ("short_only", "both") and entry.short is not None
        long_ok = want_long and entry.long is not None and self._eval(entry.long)
        short_ok = want_short and entry.short is not None and self._eval(entry.short)
        st.confirm_count_long = st.confirm_count_long + 1 if long_ok else 0
        st.confirm_count_short = st.confirm_count_short + 1 if short_ok else 0
        need = entry.confirm_bars + 1
        if st.confirm_count_long >= need and not (st.confirm_count_short >= need):
            stop, target = self._stop_target(close, "long")
            out.append(
                self._signal(
                    ts,
                    OrderSide.BUY,
                    "entry",
                    "entry.long",
                    close,
                    stop=stop,
                    target=target,
                    qty=self._suggested_qty(),
                )
            )
            st.confirm_count_long = 0
        elif st.confirm_count_short >= need and not (st.confirm_count_long >= need):
            stop, target = self._stop_target(close, "short")
            out.append(
                self._signal(
                    ts,
                    OrderSide.SELL,
                    "entry",
                    "entry.short",
                    close,
                    stop=stop,
                    target=target,
                    qty=self._suggested_qty(),
                )
            )
            st.confirm_count_short = 0
        elif long_ok and short_ok:
            reasons.append("long and short both true; no entry")
        return out

    def on_time(self, now: datetime) -> list[Signal]:
        """Clock-driven rules: intraday square-off. Call at least once a minute."""
        st = self.state
        now = ensure_utc(now)
        self._roll_session(now)
        sq = _hhmm(self.doc.session.square_off_at)
        if sq is None or st.position == "flat" or st.squared_off_today:
            return []
        if self._local(now).time() >= sq:
            st.squared_off_today = True
            side = OrderSide.SELL if st.position == "long" else OrderSide.BUY
            price = self._rows[-1]["close"] if self._rows else float(st.avg_price or 0)
            return [self._signal(now, side, "square_off", "session square-off", float(price))]
        return []

    def next_square_off(self, now: datetime) -> datetime | None:
        sq = _hhmm(self.doc.session.square_off_at)
        if sq is None:
            return None
        local = self._local(now)
        target = local.replace(hour=sq.hour, minute=sq.minute, second=0, microsecond=0)
        if target < local:
            target += timedelta(days=1)
        return ensure_utc(target)
