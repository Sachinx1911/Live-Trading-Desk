from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID, uuid4

from core.calendar import ExchangeCalendar, nse_calendar
from core.models import Candle, Quote, Signal, Timeframe, TradingMode
from core.time import IST, ensure_utc, utcnow
from execution.orders import Order
from execution.simulator.book import ClosedTrade, PositionBook
from execution.simulator.engine import ExecutionSimulator, MarketState
from execution.simulator.slippage import SpreadAwareSlippage
from risk.engine import RiskEngine, _product_for
from risk.limits import AccountState, InstrumentMeta, RiskLimits
from risk.market_history import PcrHistory
from strategy.dsl.schema import StrategyDocument
from strategy.engine import StrategyEngine
from strategy.option_features import ChainHistory

Status = Literal["paused", "playing", "ended"]
MAX_SPEED = 600
VIRTUAL_CAPITAL = Decimal("100000")
TICK = Decimal("0.05")


class _Aggregator:
    """Session-aligned incremental resampler of closed 1m bars (same semantics as the
    trader's BarAggregator, duplicated here so the API does not import the trader app)."""

    def __init__(self, tf: Timeframe, cal: ExchangeCalendar) -> None:
        if tf.duration is None:
            raise ValueError("weekly/monthly timeframes are not supported in replay")
        self.tf, self.cal = tf, cal
        self._open: Candle | None = None
        self._bucket: datetime | None = None

    def _bucket_of(self, ts: datetime) -> datetime:
        bounds = self.cal.session_bounds_utc(ts.astimezone(self.cal.tz).date())
        start = bounds[0] if bounds else ts.replace(second=0, microsecond=0)
        if self.tf == Timeframe.D1:
            return start
        dur = self.tf.duration
        assert dur is not None
        return start + int((ts - start).total_seconds() // dur.total_seconds()) * dur

    def on_1m(self, c: Candle) -> Candle | None:
        if self.tf == Timeframe.M1:
            return c
        b = self._bucket_of(c.ts)
        closed: Candle | None = None
        if self._open is not None and self._bucket != b:
            closed, self._open = self._open, None
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
                }
            )
        return closed

    def flush(self) -> Candle | None:
        c, self._open, self._bucket = self._open, None, None
        return c


def _quote(c: Candle, price: Decimal, ts: datetime) -> Quote:
    return Quote(
        instrument_id=c.instrument_id,
        ts=ts,
        ltp=price,
        bid=price - TICK,
        ask=price + TICK,
        bid_qty=10_000,
        ask_qty=10_000,
        volume=c.volume,
        oi=c.oi,
        provider_id=c.provider_id,
        provider_ts=ts,
        received_at=ts,
        is_demo=c.is_demo,
    )


@dataclass
class Overlay:
    """The paper flow, in memory, on virtual capital."""

    engine: StrategyEngine
    risk: RiskEngine
    sim: ExecutionSimulator
    book: PositionBook
    agg: _Aggregator
    meta: InstrumentMeta
    product: Any
    cal: ExchangeCalendar
    version_id: int
    pending_entry_reason: str | None = None
    # Stored PCR of the underlying (Mark 1, Stage 2): owner rules see it as of each bar.
    market_history: PcrHistory | None = None
    pending_exit_reason: str | None = None
    trades: list[dict[str, Any]] = field(default_factory=list)
    fills: list[dict[str, Any]] = field(default_factory=list)

    def account_state(self) -> AccountState:
        pos = tuple(self.book.open_positions())
        exposure = sum((abs(p.quantity) * (p.last_price or p.avg_price) for p in pos), Decimal(0))
        return AccountState(
            account_id=0,
            equity=self.book.equity,
            cash=self.book.cash,
            peak_equity=max(VIRTUAL_CAPITAL, self.book.equity),
            open_positions=pos,
            exposure=exposure,
            exposure_by_key={self.meta.correlation_key: exposure} if exposure else {},
        )

    def _handle_signal(
        self, sig: Signal, quote: Quote, ts: datetime, out: list[dict[str, Any]]
    ) -> None:
        ps = self.engine.doc.position_sizing
        if (
            sig.kind == "entry"
            and sig.suggested_quantity is not None
            and ps is not None
            and ps.method == "fixed_lots"
        ):
            sig = sig.model_copy(
                update={"suggested_quantity": sig.suggested_quantity * self.meta.lot_size}
            )
        out.append({"type": "signal", **_sig_dict(sig)})
        decision = self.risk.evaluate(
            sig,
            self.account_state(),
            self.meta,
            quote,
            now=ts,
            calendar=self.cal,
            kill_switch_active=False,
            mode=TradingMode.PAPER,
            product=self.product,
            market=self.market_history.context_at(ts) if self.market_history is not None else None,
        )
        if not decision.allowed or decision.intent is None:
            out.append(
                {"type": "signal_rejected", "kind": sig.kind, "reasons": list(decision.reasons)}
            )
            return
        order = self.sim.submit(decision.intent, MarketState(ts=ts, quote=quote))
        if sig.kind == "entry":
            self.pending_entry_reason = sig.reason
        else:
            self.pending_exit_reason = f"{sig.kind}: {sig.reason}"
        out.append({"type": "order", **_order_dict(order)})

    def market(self, c: Candle, out: list[dict[str, Any]]) -> None:
        """Fills for orders created on the previous bar, at this bar's open."""
        q = _quote(c, c.open, c.ts)
        self.book.mark(c.instrument_id, c.open)
        for fill in self.sim.on_market(c.instrument_id, MarketState(ts=c.ts, quote=q)):
            order = self.sim.orders[fill.order_id]
            closed = self.book.apply(order, fill)
            pos = self.book.position(c.instrument_id)
            self.engine.set_position(pos.quantity, None if pos.is_flat else pos.avg_price)
            f = {
                "type": "fill",
                "order_id": str(fill.order_id),
                "ts": fill.ts.isoformat(),
                "side": order.intent.side.value,
                "quantity": fill.quantity,
                "price": str(fill.price),
                "costs": str(fill.costs),
            }
            self.fills.append(f)
            out.append(f)
            out.append({"type": "order", **_order_dict(order)})
            out.append({"type": "position", **_pos_dict(pos)})
            if closed is not None:
                t = _trade_dict(closed, self.pending_entry_reason, self.pending_exit_reason)
                self.trades.append(t)
                out.append({"type": "trade", **t})

    def bar(self, c: Candle, out: list[dict[str, Any]]) -> None:
        """Strategy evaluation on the bar close; orders rest until the next bar's open."""
        closed = self.agg.on_1m(c)
        if closed is None:
            return
        close_ts = c.ts + timedelta(minutes=1)
        q = _quote(c, c.close, close_ts)
        self.book.mark(c.instrument_id, c.close)
        for sig in self.engine.on_candle(closed):
            self._handle_signal(sig, q, close_ts, out)
        for sig in self.engine.on_time(close_ts):
            self._handle_signal(sig, q, close_ts, out)

    def warm(self, bars_1m: Sequence[Candle]) -> int:
        n = 0
        for c in bars_1m:
            closed = self.agg.on_1m(c)
            if closed is not None:
                self.engine.on_candle(closed)
                n += 1
        return n

    def state(self) -> dict[str, Any]:
        pos = self.book.open_positions()
        return {
            "equity": str(self.book.equity),
            "cash": str(self.book.cash),
            "realized": str(self.book.realized),
            "unrealized": str(self.book.unrealized),
            "position": _pos_dict(pos[0]) if pos else None,
            "trades": len(self.trades),
            "engine": self.engine.state.position,
        }


def _sig_dict(s: Signal) -> dict[str, Any]:
    return {
        "signal_id": str(s.signal_id),
        "ts": s.ts.isoformat(),
        "side": s.side.value,
        "kind": s.kind,
        "reason": s.reason,
        "reference_price": str(s.reference_price),
        "stop_price": None if s.stop_price is None else str(s.stop_price),
        "target_price": None if s.target_price is None else str(s.target_price),
    }


def _order_dict(o: Order) -> dict[str, Any]:
    return {
        "order_id": str(o.order_id),
        "side": o.intent.side.value,
        "order_type": o.intent.order_type.value,
        "quantity": o.intent.quantity,
        "filled_qty": o.filled_qty,
        "status": o.status.value,
        "avg_fill_price": None if o.avg_fill_price is None else str(o.avg_fill_price),
        "created_at": o.created_at.isoformat(),
    }


def _pos_dict(p: Any) -> dict[str, Any]:
    return {
        "instrument_id": p.instrument_id,
        "quantity": p.quantity,
        "avg_price": str(p.avg_price),
        "realized_pnl": str(p.realized_pnl),
        "unrealized_pnl": str(p.unrealized_pnl),
        "last_price": None if p.last_price is None else str(p.last_price),
    }


def _trade_dict(
    t: ClosedTrade, entry_reason: str | None, exit_reason: str | None
) -> dict[str, Any]:
    return {
        "side": t.side.value,
        "quantity": t.quantity,
        "entry_at": t.entry_at.isoformat(),
        "entry_price": str(t.entry_price),
        "exit_at": t.exit_at.isoformat(),
        "exit_price": str(t.exit_price),
        "gross_pnl": str(t.gross_pnl),
        "costs": str(t.costs),
        "net_pnl": str(t.net_pnl),
        "entry_reason": entry_reason,
        "exit_reason": exit_reason,
    }


class ReplaySession:
    def __init__(
        self,
        *,
        user_id: int,
        instrument_id: int,
        day: date,
        timeframe: Timeframe,
        candles_1m: Sequence[Candle],
        warmup_1m: Sequence[Candle] = (),
        strategy: StrategyDocument | None = None,
        strategy_version_id: int | None = None,
        meta: InstrumentMeta | None = None,
        speed: float = 10.0,
        seed: int | None = None,
        calendar: ExchangeCalendar | None = None,
        market_history: PcrHistory | None = None,
        option_history: ChainHistory | None = None,
    ) -> None:
        self.session_id: str = uuid4().hex[:12]
        self.market_history = market_history
        self.option_history = option_history
        self.user_id = user_id
        self.instrument_id = instrument_id
        self.day = day
        self.timeframe = timeframe
        self.cal = calendar or nse_calendar()
        self.bars = sorted(candles_1m, key=lambda c: c.ts)
        self.warmup_1m = sorted(warmup_1m, key=lambda c: c.ts)
        self.strategy = strategy
        self.version_id = strategy_version_id
        self.meta = meta
        self.seed = (
            seed if seed is not None else int(UUID(self.session_id.ljust(32, "0")).int % 10_000)
        )
        self.speed = max(0.1, min(float(speed), MAX_SPEED))
        self.cursor = 0  # number of 1m bars consumed
        self.status: Status = "paused"
        self.created_at = utcnow()
        self.last_activity = self.created_at
        self._subs: list[asyncio.Queue[dict[str, Any]]] = []
        self._task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()
        self.view_agg = _Aggregator(timeframe, self.cal)
        self.overlay: Overlay | None = None
        self.warmup_bars = 0
        self._build(0)

    # ------------------------------------------------------------------ construction
    def _make_overlay(self) -> Overlay | None:
        if self.strategy is None or self.meta is None or self.version_id is None:
            return None
        engine = StrategyEngine(
            self.strategy,
            self.instrument_id,
            self.cal,
            self.version_id,
            option_provider=self.option_history.at if self.option_history is not None else None,
        )
        sim = ExecutionSimulator(
            slippage=SpreadAwareSlippage(base_bps=2, size_impact_per_lot=0.5),
            seed=self.seed,
            calendar=self.cal,
            lot_size_of={self.instrument_id: self.meta.lot_size},
            segment_of={self.instrument_id: self.meta.segment},
        )
        return Overlay(
            engine=engine,
            risk=RiskEngine(RiskLimits()),
            sim=sim,
            book=PositionBook(account_id=0, mode=TradingMode.PAPER, initial_cash=VIRTUAL_CAPITAL),
            agg=_Aggregator(Timeframe(self.strategy.timeframe), self.cal),
            meta=self.meta,
            product=_product_for(self.meta, True),
            cal=self.cal,
            version_id=self.version_id,
            market_history=self.market_history,
        )

    def _build(self, upto: int) -> None:
        """Rebuild all state deterministically from the start up to `upto` 1m bars."""
        self.view_agg = _Aggregator(self.timeframe, self.cal)
        self.overlay = self._make_overlay()
        if self.overlay is not None:
            self.warmup_bars = self.overlay.warm(self.warmup_1m)
        self.cursor = 0
        sink: list[dict[str, Any]] = []
        for _ in range(min(upto, len(self.bars))):
            self._advance(sink)
        self.status = "ended" if self.cursor >= len(self.bars) else "paused"

    # ------------------------------------------------------------------ stepping
    def _advance(self, out: list[dict[str, Any]]) -> None:
        c = self.bars[self.cursor]
        if self.overlay is not None:
            self.overlay.market(c, out)
        view = self.view_agg.on_1m(c)
        if view is not None:
            out.append({"type": "bar", **view.model_dump(mode="json")})
        out.append(
            {
                "type": "quote",
                **_quote(c, c.close, c.ts + timedelta(minutes=1)).model_dump(mode="json"),
            }
        )
        if self.overlay is not None:
            self.overlay.bar(c, out)
        self.cursor += 1
        if self.cursor >= len(self.bars):
            tail = self.view_agg.flush()
            if tail is not None:
                out.append({"type": "bar", **tail.model_dump(mode="json")})
            self.status = "ended"

    def state(self) -> dict[str, Any]:
        cur = (
            self.bars[self.cursor - 1].ts + timedelta(minutes=1)
            if self.cursor
            else (self.bars[0].ts if self.bars else None)
        )
        return {
            "type": "state",
            "session_id": self.session_id,
            "status": self.status,
            "speed": self.speed,
            "cursor": self.cursor,
            "bars": len(self.bars),
            "cursor_ts": cur.isoformat() if cur else None,
            "warmup_bars": self.warmup_bars,
            "overlay": self.overlay.state() if self.overlay else None,
        }

    async def _emit(self, events: list[dict[str, Any]]) -> None:
        events.append(self.state())
        for q in list(self._subs):
            for e in events:
                q.put_nowait(e)

    async def step(self, n: int = 1) -> dict[str, Any]:
        self.last_activity = utcnow()
        async with self._lock:
            out: list[dict[str, Any]] = []
            if n >= 0:
                for _ in range(n):
                    if self.cursor >= len(self.bars):
                        break
                    self._advance(out)
            else:
                self._build(max(0, self.cursor + n))
                out.append({"type": "rewound", "cursor": self.cursor})
            await self._emit(out)
            return self.state()

    async def seek(self, ts: datetime) -> dict[str, Any]:
        ts = ensure_utc(ts)
        target = sum(1 for c in self.bars if c.ts < ts)
        self.last_activity = utcnow()
        async with self._lock:
            if target < self.cursor:
                self._build(target)
                out: list[dict[str, Any]] = [{"type": "rewound", "cursor": self.cursor}]
            else:
                out = []
                while self.cursor < target:
                    self._advance(out)
            await self._emit(out)
            return self.state()

    async def _run(self) -> None:
        try:
            while self.status == "playing" and self.cursor < len(self.bars):
                await self.step(1)
                await asyncio.sleep(60.0 / self.speed)
        finally:
            if self.status == "playing":
                self.status = "paused"
            await self._emit([])

    def play(self) -> dict[str, Any]:
        self.last_activity = utcnow()
        if self.status != "ended" and (self._task is None or self._task.done()):
            self.status = "playing"
            self._task = asyncio.create_task(self._run())
        return self.state()

    async def pause(self) -> dict[str, Any]:
        self.last_activity = utcnow()
        if self.status == "playing":
            self.status = "paused"
        if self._task is not None and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        return self.state()

    def set_speed(self, x: float) -> dict[str, Any]:
        self.speed = max(0.1, min(float(x), MAX_SPEED))
        return self.state()

    async def control(self, msg: dict[str, Any]) -> dict[str, Any]:
        action = msg.get("action") or msg.get("type")
        if action == "play":
            return self.play()
        if action == "pause":
            return await self.pause()
        if action in ("set_speed", "speed"):
            return self.set_speed(float(msg.get("x") or msg.get("speed") or self.speed))
        if action == "step":
            return await self.step(int(msg.get("n", msg.get("bars", 1))))
        if action == "seek":
            return await self.seek(datetime.fromisoformat(str(msg["ts"])))
        raise ValueError(f"unknown action {action!r}")

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=10_000)
        self._subs.append(q)
        q.put_nowait(self.state())
        return q

    def unsubscribe(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        with contextlib.suppress(ValueError):
            self._subs.remove(q)

    async def close(self) -> None:
        await self.pause()
        self._subs.clear()

    @property
    def day_label(self) -> str:
        return self.day.isoformat()

    @staticmethod
    def session_day(ts: datetime) -> date:
        return ts.astimezone(IST).date()
