"""The backtest loop. Mirrors apps/trader/runner.py decision for decision:

    closed bar -> StrategyEngine.on_candle -> Signal
    -> RiskEngine.evaluate (same limits, same sizing) -> OrderIntent
    -> ExecutionSimulator.submit -> fill on the next market event -> PositionBook.apply
    -> engine.set_position; engine.on_time at every bar close for square-off.

Differences from paper are only the clock and the data source (ADR-002)."""

from __future__ import annotations

import time as _time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import UUID

from backtest.config import BacktestConfig
from backtest.data import HistoricalFeed
from backtest.metrics import (
    Metrics,
    compute_metrics,
    daily_returns,
    drawdown_curve,
    monthly_table,
)
from core.calendar import ExchangeCalendar, nse_calendar
from core.models import Candle, Instrument, OrderSide, Quote, Signal, Timeframe, TradingMode
from core.time import IST, ensure_utc
from execution.costs import CostModel, RowSchedule, StaticCostSchedule
from execution.orders import Order
from execution.simulator.book import ClosedTrade, PositionBook
from execution.simulator.engine import ExecutionSimulator, MarketState
from execution.simulator.slippage import FixedBpsSlippage, SlippageModel, SpreadAwareSlippage
from risk.engine import RiskEngine, _product_for
from risk.limits import AccountState, InstrumentMeta
from risk.market_history import PcrHistory
from strategy.engine import RegimeProvider, StrategyEngine
from strategy.option_features import ChainHistory
from strategy.regime import RegimeDaily, RegimeDetector, provider_from_regimes, regime_table

ProgressFn = Callable[[float], None]


@dataclass(frozen=True)
class TradeRecord:
    instrument_id: int
    strategy_version_id: int | None
    side: OrderSide
    quantity: int
    entry_at: datetime
    entry_price: Decimal
    exit_at: datetime
    exit_price: Decimal
    gross_pnl: Decimal
    costs: Decimal
    net_pnl: Decimal
    entry_reason: str | None
    exit_reason: str | None
    bars_held: int | None
    mae: Decimal | None  # max adverse excursion per unit (<= 0)
    mfe: Decimal | None  # max favourable excursion per unit (>= 0)
    bar_index_entry: int | None
    bar_index_exit: int | None
    regime: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "instrument_id": self.instrument_id,
            "strategy_version_id": self.strategy_version_id,
            "side": self.side.value,
            "quantity": self.quantity,
            "entry_at": self.entry_at.isoformat(),
            "entry_price": str(self.entry_price),
            "exit_at": self.exit_at.isoformat(),
            "exit_price": str(self.exit_price),
            "gross_pnl": str(self.gross_pnl),
            "costs": str(self.costs),
            "net_pnl": str(self.net_pnl),
            "entry_reason": self.entry_reason,
            "exit_reason": self.exit_reason,
            "bars_held": self.bars_held,
            "mae": None if self.mae is None else str(self.mae),
            "mfe": None if self.mfe is None else str(self.mfe),
            "bar_index_entry": self.bar_index_entry,
            "bar_index_exit": self.bar_index_exit,
            "regime": self.regime,
        }


@dataclass
class BacktestResult:
    config_hash: str
    data_hash: str
    assumptions: dict[str, Any]
    metrics: Metrics
    trades: list[TradeRecord]
    equity_curve: list[tuple[datetime, Decimal]]  # one point per session close
    drawdown_curve: list[tuple[datetime, float]]
    daily_returns: list[float]
    monthly_table: list[dict[str, Any]]
    bar_equity: list[tuple[datetime, Decimal]]
    stats: dict[str, Any]
    warnings: list[str]
    elapsed_s: float
    bars: int
    regime_table: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "config_hash": self.config_hash,
            "data_hash": self.data_hash,
            "assumptions": self.assumptions,
            "metrics": self.metrics.as_dict(),
            "trades": [t.as_dict() for t in self.trades],
            "equity_curve": [(ts.isoformat(), str(eq)) for ts, eq in self.equity_curve],
            "drawdown_curve": [(ts.isoformat(), dd) for ts, dd in self.drawdown_curve],
            "daily_returns": self.daily_returns,
            "monthly_table": self.monthly_table,
            "stats": self.stats,
            "warnings": self.warnings,
            "elapsed_s": self.elapsed_s,
            "bars": self.bars,
            "regime_table": self.regime_table,
        }


@dataclass
class _Excursion:
    entry_price: Decimal
    side: OrderSide
    worst: Decimal = Decimal(0)
    best: Decimal = Decimal(0)
    entry_bar: int = 0
    entry_reason: str | None = None

    def update(self, high: Decimal, low: Decimal) -> None:
        if self.side == OrderSide.BUY:
            self.worst = min(self.worst, low - self.entry_price)
            self.best = max(self.best, high - self.entry_price)
        else:
            self.worst = min(self.worst, self.entry_price - high)
            self.best = max(self.best, self.entry_price - low)


@dataclass
class _State:
    realized_day: Decimal = Decimal(0)
    realized_week: Decimal = Decimal(0)
    day: date | None = None
    week: tuple[int, int] | None = None
    halted_reason: str | None = None
    halted_day: date | None = None
    last_entry_reason: str | None = None
    last_exit_reason: str | None = None
    signals: int = 0
    rejections: dict[str, int] = field(default_factory=dict)
    gate: dict[str, int] = field(default_factory=dict)
    orders_rejected: int = 0
    bars_in_position: int = 0
    excursion: _Excursion | None = None
    order_reason: dict[UUID, str] = field(default_factory=dict)


def _slippage(cfg: BacktestConfig) -> SlippageModel:
    if cfg.slippage.model == "spread_aware":
        return SpreadAwareSlippage(
            cfg.slippage.bps, cfg.slippage.size_impact_per_lot, seed=cfg.seed
        )
    return FixedBpsSlippage(cfg.slippage.bps)


def _cost_model(cfg: BacktestConfig) -> CostModel:
    if cfg.cost_schedule == "rows" and cfg.cost_rows:
        rows = [
            SimpleNamespace(
                product=r.product,
                charge_type=r.charge_type,
                side=r.side,
                rate_type=r.rate_type,
                rate=r.rate,
                cap=r.cap,
                effective_from=date.fromisoformat(r.effective_from),
                effective_to=date.fromisoformat(r.effective_to) if r.effective_to else None,
            )
            for r in cfg.cost_rows
        ]
        return CostModel(RowSchedule(rows))
    return CostModel(StaticCostSchedule())


def _meta(ins: Instrument, lot_size: int) -> InstrumentMeta:
    return InstrumentMeta(
        instrument_id=ins.instrument_id,
        symbol=ins.symbol,
        segment=ins.segment,
        lot_size=lot_size,
        tick_size=ins.tick_size,
        underlying_symbol=ins.underlying_symbol,
        option_type=ins.option_type,
    )


def _account_state(
    book: PositionBook, st: _State, account_id: int, hwm: Decimal, meta: InstrumentMeta
) -> AccountState:
    positions = tuple(book.open_positions())
    exposure = sum((abs(p.quantity) * (p.last_price or p.avg_price) for p in positions), Decimal(0))
    by_key: dict[str, Decimal] = {}
    for p in positions:
        by_key[meta.correlation_key] = by_key.get(meta.correlation_key, Decimal(0)) + abs(
            p.quantity
        ) * (p.last_price or p.avg_price)
    return AccountState(
        account_id=account_id,
        equity=book.equity,
        cash=book.cash,
        realized_today=st.realized_day,
        realized_week=st.realized_week,
        peak_equity=max(hwm, book.equity),
        open_positions=positions,
        exposure=exposure,
        exposure_by_key=by_key,
    )


def _daily_regimes(candles: Sequence[Candle], cal: ExchangeCalendar) -> dict[date, RegimeDaily]:
    """Regime per session from the backtest's own series (resampled to daily, no VIX →
    ATR-based volatility). Point-in-time: the regime for day D uses bars up to D's close and is
    applied to trades on D+1 onwards by `provider_from_regimes` (it keys on date <= ts date,
    so we store it under the NEXT session's date)."""
    by_day: dict[date, list[Candle]] = {}
    for c in candles:
        by_day.setdefault(ensure_utc(c.ts).astimezone(IST).date(), []).append(c)
    daily: list[Candle] = []
    for d in sorted(by_day):
        bars = sorted(by_day[d], key=lambda c: c.ts)
        daily.append(
            Candle(
                instrument_id=bars[0].instrument_id,
                timeframe=Timeframe.D1,
                ts=bars[0].ts,
                open=bars[0].open,
                high=max(b.high for b in bars),
                low=min(b.low for b in bars),
                close=bars[-1].close,
                volume=sum(b.volume for b in bars),
                provider_id=bars[0].provider_id,
                received_at=bars[-1].received_at,
                is_demo=bars[0].is_demo,
            )
        )
    det = RegimeDetector()
    out: dict[date, RegimeDaily] = {}
    for i in range(30, len(daily) + 1):
        window = daily[max(0, i - 260) : i]
        r = det.daily(window)
        out[cal.next_trading_day(r.date)] = r
    return out


def _regime_tag(provider: RegimeProvider | None, ts: datetime) -> dict[str, Any] | None:
    if provider is None:
        return None
    ctx = provider(ts) or {}
    keys = (
        "trend",
        "strength",
        "volatility",
        "structure",
        "day_type",
        "adx",
        "vix",
        "regime_label",
    )
    return {k: ctx.get(k) for k in keys if k in ctx} or None


def run_backtest(
    cfg: BacktestConfig,
    candles: Sequence[Candle],
    *,
    regime_provider: RegimeProvider | None = None,
    progress: ProgressFn | None = None,
    calendar: ExchangeCalendar | None = None,
    market_history: PcrHistory | None = None,
    option_history: ChainHistory | None = None,
) -> BacktestResult:
    """`market_history`: stored PCR of the traded option's underlying (Mark 1, Stage 2). When
    given, owner rules see the PCR as it was at each simulated moment (never later); when None
    (no chain history stored for the range) rules that need it report `skipped`, and the
    assumptions say so."""
    t0 = _time.perf_counter()
    cal = calendar or nse_calendar()
    doc = cfg.document()
    tf = cfg.effective_timeframe
    ins = cfg.instrument
    lot = cfg.effective_lot_size
    meta = _meta(ins, lot)
    product = _product_for(meta, True)
    account_id = -cfg.strategy_version_id  # synthetic, never collides with DB accounts

    feed = HistoricalFeed(
        candles,
        tf,
        cal,
        tick_size=ins.tick_size,
        start=cfg.start,
        end=cfg.end,
        fill_mode=cfg.fill_mode,
    )
    regimes_by_day: dict[date, RegimeDaily] = {}
    if regime_provider is None:
        regimes_by_day = _daily_regimes(candles, cal)
        regime_provider = provider_from_regimes(regimes_by_day)
    engine = StrategyEngine(
        doc,
        ins.instrument_id,
        cal,
        cfg.strategy_version_id,
        regime_provider,
        option_provider=option_history.at if option_history is not None else None,
    )
    risk = RiskEngine(cfg.risk_limits)
    sim = ExecutionSimulator(
        _cost_model(cfg),
        _slippage(cfg),
        seed=cfg.seed,
        calendar=cal,
        lot_size_of={ins.instrument_id: lot},
        segment_of={ins.instrument_id: ins.segment},
    )
    book = PositionBook(
        account_id=account_id, mode=TradingMode.PAPER, initial_cash=cfg.initial_capital
    )
    st = _State()
    warnings: list[str] = []
    trades: list[TradeRecord] = []
    equity_curve: list[tuple[datetime, Decimal]] = []
    bar_equity: list[tuple[datetime, Decimal]] = []
    hwm = cfg.initial_capital
    warmup = engine.warmup_bars
    total_bars = len(feed)
    if total_bars <= warmup:
        warnings.append(f"only {total_bars} bars; {warmup} needed for warm-up: no trading possible")
    bars_seen = 0
    last_candle: Candle | None = None
    quote_now: Quote | None = None

    # ------------------------------------------------------------------ helpers
    def roll_periods(ts: datetime) -> None:
        local = ts.astimezone(cal.tz)
        d = local.date()
        wk = d.isocalendar()[:2]
        if st.day != d:
            st.day = d
            st.realized_day = Decimal(0)
            if st.halted_day != d:
                st.halted_reason = None
        if st.week != wk:
            st.week = wk
            st.realized_week = Decimal(0)

    def handle_signal(sig: Signal, now: datetime, candle: Candle | None) -> None:
        nonlocal hwm
        st.signals += 1
        if sig.kind == "entry" and st.halted_reason is not None:
            st.rejections["halted: " + st.halted_reason] = (
                st.rejections.get("halted: " + st.halted_reason, 0) + 1
            )
            return
        ps = doc.position_sizing
        if (
            sig.kind == "entry"
            and sig.suggested_quantity is not None
            and ps is not None
            and ps.method == "fixed_lots"
        ):
            sig = sig.model_copy(update={"suggested_quantity": sig.suggested_quantity * lot})
        decision = risk.evaluate(
            sig,
            _account_state(book, st, account_id, hwm, meta),
            meta,
            quote_now,
            now=now,
            calendar=cal,
            kill_switch_active=False,
            mode=TradingMode.PAPER,
            product=product,
            market=market_history.context_at(now) if market_history is not None else None,
        )
        if not decision.allowed or decision.intent is None:
            for r in decision.reasons:
                st.rejections[r] = st.rejections.get(r, 0) + 1
            return
        order = sim.submit(decision.intent, MarketState(ts=now, quote=quote_now, candle=candle))
        if order.order_id in st.order_reason:
            return
        st.order_reason[order.order_id] = f"{sig.kind}: {sig.reason}"
        if order.status.value == "rejected":
            st.orders_rejected += 1
            return
        if sig.kind == "entry":
            st.last_entry_reason = sig.reason
        else:
            st.last_exit_reason = f"{sig.kind}: {sig.reason}"

    def process_fills(market: MarketState, bar_index: int) -> None:
        nonlocal hwm
        for fill in sim.on_market(ins.instrument_id, market):
            order: Order = sim.orders[fill.order_id]
            was_flat = book.position(ins.instrument_id).is_flat
            closed: ClosedTrade | None = book.apply(order, fill)
            pos = book.position(ins.instrument_id)
            engine.set_position(pos.quantity, None if pos.is_flat else pos.avg_price)
            if was_flat and not pos.is_flat:
                st.excursion = _Excursion(
                    entry_price=fill.price,
                    side=order.intent.side,
                    entry_bar=bar_index,
                    entry_reason=st.last_entry_reason,
                )
            if closed is not None:
                ex = st.excursion
                trades.append(
                    TradeRecord(
                        instrument_id=closed.instrument_id,
                        strategy_version_id=closed.strategy_version_id,
                        side=closed.side,
                        quantity=closed.quantity,
                        entry_at=closed.entry_at,
                        entry_price=closed.entry_price,
                        exit_at=closed.exit_at,
                        exit_price=closed.exit_price,
                        gross_pnl=closed.gross_pnl,
                        costs=closed.costs,
                        net_pnl=closed.net_pnl,
                        entry_reason=ex.entry_reason if ex else st.last_entry_reason,
                        exit_reason=st.order_reason.get(order.order_id, st.last_exit_reason),
                        bars_held=(bar_index - ex.entry_bar) if ex else None,
                        mae=ex.worst if ex else None,
                        mfe=ex.best if ex else None,
                        bar_index_entry=ex.entry_bar if ex else None,
                        bar_index_exit=bar_index,
                        regime=_regime_tag(regime_provider, closed.entry_at),
                    )
                )
                st.excursion = None
                st.realized_day += closed.net_pnl
                st.realized_week += closed.net_pnl
                check_loss_limits(market.ts)
            hwm = max(hwm, book.equity)

    def check_loss_limits(now: datetime) -> None:
        lim = cfg.risk_limits
        day_cap = -cfg.initial_capital * Decimal(str(lim.max_daily_loss_pct)) / 100
        week_cap = -cfg.initial_capital * Decimal(str(lim.max_weekly_loss_pct)) / 100
        why = None
        if st.realized_day <= day_cap:
            why = "daily loss limit"
        elif st.realized_week <= week_cap:
            why = "weekly loss limit"
        if why and st.halted_reason is None:
            st.halted_reason = why
            st.halted_day = now.astimezone(cal.tz).date()
            st.gate[why] = st.gate.get(why, 0) + 1
            square_off(now, f"{why}: flattening")

    def square_off(now: datetime, why: str) -> None:
        pos = book.position(ins.instrument_id)
        if pos.is_flat:
            return
        ref = quote_now.ltp if quote_now else pos.avg_price
        sig = Signal(
            strategy_version_id=cfg.strategy_version_id,
            instrument_id=ins.instrument_id,
            ts=now,
            side=OrderSide.SELL if pos.quantity > 0 else OrderSide.BUY,
            kind="square_off",
            reason=why,
            reference_price=ref,
            suggested_quantity=abs(pos.quantity),
        )
        handle_signal(sig, now, last_candle)

    # ------------------------------------------------------------------ main loop
    bar_index = -1
    for ev in feed.events():
        if ev.kind == "bar":
            assert ev.candle is not None
            c = ev.candle
            bar_index += 1
            bars_seen += 1
            last_candle = c
            roll_periods(ev.ts)
            book.mark(ins.instrument_id, c.close)
            if st.excursion is not None:
                st.excursion.update(c.high, c.low)
            if not book.position(ins.instrument_id).is_flat:
                st.bars_in_position += 1
            signals = engine.on_candle(c)
            for r in engine.state.rejections:
                st.gate[r] = st.gate.get(r, 0) + 1
            if bars_seen <= warmup:
                continue  # warm-up: indicators only, no trading
            for sig in signals:
                handle_signal(sig, ev.ts, c)
            for sig in engine.on_time(ev.ts):
                handle_signal(sig, ev.ts, c)
            if cfg.keep_bar_equity:
                bar_equity.append((ev.ts, book.equity))
            if progress is not None and total_bars and bar_index % 500 == 0:
                progress(min(99.0, bar_index / total_bars * 100))
        elif ev.kind in ("open", "close"):
            assert ev.quote is not None
            quote_now = ev.quote
            process_fills(MarketState(ts=ev.ts, quote=ev.quote), bar_index)
        elif ev.kind == "session_end":
            # Orders cannot survive the session; cancel what is still working.
            for o in sim.open_orders(ins.instrument_id):
                sim.cancel(o.order_id, "session closed", ts=ev.ts)
            equity_curve.append((ev.ts, book.equity))

    # end of data: flatten anything still open at the last close (one synthetic print)
    flattened = False
    if last_candle is not None and not book.position(ins.instrument_id).is_flat:
        close_ts = equity_curve[-1][0] if equity_curve else ensure_utc(last_candle.ts)
        quote_now = Quote(
            instrument_id=ins.instrument_id,
            ts=close_ts,
            ltp=last_candle.close,
            provider_id=last_candle.provider_id,
            received_at=close_ts,
            is_demo=last_candle.is_demo,
        )
        square_off(close_ts, "end of data")
        fill_ts = close_ts + timedelta(seconds=1)
        process_fills(
            MarketState(ts=fill_ts, quote=quote_now.model_copy(update={"ts": fill_ts})), bar_index
        )
        flattened = True
        if equity_curve:
            equity_curve[-1] = (equity_curve[-1][0], book.equity)
        warnings.append("open position flattened at the last close (end of data)")

    if not equity_curve and last_candle is not None:
        equity_curve.append((ensure_utc(last_candle.ts), book.equity))

    metrics = compute_metrics(
        trades,
        equity_curve,
        initial_capital=cfg.initial_capital,
        bars_total=max(0, bars_seen - warmup),
        bars_in_position=st.bars_in_position,
    )
    assumptions = cfg.assumptions()
    assumptions["end_of_data_flatten"] = flattened
    assumptions["warmup_bars"] = warmup
    if option_history is not None:
        assumptions["option_chain_snapshots"] = len(option_history)
    assumptions["owner_rules_market_data"] = (
        {
            "pcr_points": len(market_history),
            "first_ts": market_history.first_ts.isoformat() if market_history.first_ts else None,
            "last_ts": market_history.last_ts.isoformat() if market_history.last_ts else None,
        }
        if market_history is not None
        else "none: rules that need option-chain history were skipped"
    )
    assumptions["bars"] = total_bars
    assumptions["data_hash"] = feed.source_hash
    if progress is not None:
        progress(100.0)
    return BacktestResult(
        config_hash=cfg.config_hash(),
        data_hash=feed.source_hash,
        assumptions=assumptions,
        metrics=metrics,
        trades=trades,
        equity_curve=equity_curve,
        drawdown_curve=drawdown_curve(equity_curve),
        daily_returns=daily_returns(equity_curve),
        monthly_table=monthly_table(equity_curve),
        bar_equity=bar_equity,
        stats={
            "signals": st.signals,
            "risk_rejections": st.rejections,
            "engine_gate": st.gate,
            "orders_rejected_by_simulator": st.orders_rejected,
            "orders": len(sim.orders),
            "bars_in_position": st.bars_in_position,
            "halted": st.halted_reason,
        },
        warnings=warnings,
        elapsed_s=round(_time.perf_counter() - t0, 3),
        bars=total_bars,
        regime_table=regime_table(trades, lambda t: t.regime),
    )
