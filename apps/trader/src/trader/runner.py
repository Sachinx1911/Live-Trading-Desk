"""Paper trading runner.

One process, many activations. For each active (version, paper account, instrument):
  Redis market.candle (1m) -> BarAggregator -> StrategyEngine.on_candle -> Signal
  -> RiskEngine.evaluate -> OrderIntent -> ExecutionSimulator.submit
  Redis market.tick -> ExecutionSimulator.on_market -> Fill -> PositionBook -> DB

Hard rules enforced here (not by the strategy): kill switch, daily/weekly loss limits,
session square-off, no new entries after cutoff. When a loss limit is hit the account's
activations are PAUSED with a reason and the owner is notified.
"""

from __future__ import annotations

import asyncio
import contextlib
import signal as os_signal
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import orjson
from redis.asyncio import Redis

from core.calendar import ExchangeCalendar, nse_calendar
from core.db import get_session_factory
from core.db.models import PaperAccount
from core.db.models._enums import ActivationStatus, RiskLimitScope
from core.logging import configure_logging, get_logger
from core.models import Candle, OrderSide, Quote, Signal, Timeframe, TradingMode
from core.notify import build_notifier
from core.settings import Settings, get_settings
from core.time import IST, utcnow
from execution.orders import Order
from execution.simulator.book import PositionBook
from execution.simulator.engine import ExecutionSimulator, MarketState
from execution.simulator.slippage import SpreadAwareSlippage
from market_data.repo.candles import fetch_candles
from market_data.repo.instruments import get_instrument
from market_data.repo.regime import latest_daily, latest_intraday
from risk.engine import RiskEngine
from risk.kill_switch import KillSwitch
from risk.limits import AccountState, InstrumentMeta, RiskLimits
from strategy.dsl.schema import StrategyDocument
from strategy.engine import StrategyEngine
from strategy.regime import RegimeDaily, RegimeIntraday
from trader import store
from trader.bars import BarAggregator

log = get_logger("trader")

REFRESH_EVERY = timedelta(seconds=10)
SNAPSHOT_EVERY = timedelta(seconds=60)


@dataclass
class Runner:
    """Everything for one activation."""

    activation_id: int
    version_id: int
    account_id: int
    instrument_id: int
    engine: StrategyEngine
    bars: BarAggregator
    meta: InstrumentMeta
    product: Any
    limits: RiskLimits
    risk: RiskEngine
    last_entry_reason: str | None = None
    last_exit_reason: str | None = None
    entry_bar_count: int = 0
    paused: bool = False
    flatten_requested: bool = False
    last_rejections: tuple[str, ...] = ()
    regime_daily: RegimeDaily | None = None
    regime_intraday: RegimeIntraday | None = None
    regime_loaded_at: datetime | None = None


@dataclass
class AccountCtx:
    account: PaperAccount
    book: PositionBook
    sim: ExecutionSimulator
    row_ids: dict[UUID, int] = field(default_factory=dict)
    events_synced: dict[UUID, int] = field(default_factory=dict)
    order_runner: dict[UUID, int] = field(default_factory=dict)  # order -> activation id
    realized_day: Decimal = Decimal("0")
    realized_week: Decimal = Decimal("0")
    halted_reason: str | None = None


class Trader:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.redis = Redis.from_url(settings.redis_url, decode_responses=False)
        self.cal: ExchangeCalendar = nse_calendar()
        self.notifier = build_notifier(settings)
        self.ks = KillSwitch(Redis.from_url(settings.redis_url, decode_responses=True))
        self.runners: dict[int, Runner] = {}
        self.accounts: dict[int, AccountCtx] = {}
        self.quotes: dict[int, Quote] = {}
        self._stop = asyncio.Event()
        self._last_refresh: datetime | None = None
        self._last_snapshot: datetime | None = None

    # ------------------------------------------------------------------ setup
    async def _account_ctx(self, acc: PaperAccount, db: Any) -> AccountCtx:
        ctx = self.accounts.get(acc.id)
        if ctx is not None:
            ctx.account = acc
            return ctx
        book = PositionBook(account_id=acc.id, mode=TradingMode.PAPER, initial_cash=acc.cash)
        sim = ExecutionSimulator(
            slippage=SpreadAwareSlippage(base_bps=2, size_impact_per_lot=0.5),
            seed=acc.id,
            calendar=self.cal,
        )
        ctx = AccountCtx(account=acc, book=book, sim=sim)
        today = utcnow().astimezone(IST).date()
        ctx.realized_day = await store.realized_since(db, acc.id, store.day_start_utc(today))
        ctx.realized_week = await store.realized_since(db, acc.id, store.week_start_utc(today))
        self.accounts[acc.id] = ctx
        return ctx

    async def _warmup(self, r: Runner, db: Any) -> int:
        """Feed recent closed bars so indicators are ready before the first live bar."""
        tf = Timeframe(r.engine.doc.timeframe)
        need = max(r.engine.warmup_bars + 5, 30)
        end = utcnow()
        # Look back across sessions (intraday history is sparse per calendar hour), then slice.
        start = end - (timedelta(days=400) if not tf.is_intraday else timedelta(days=10))
        bars = await fetch_candles(db, r.instrument_id, tf, start, end)
        if not bars and tf.value != "1m":
            ones = await fetch_candles(db, r.instrument_id, Timeframe.M1, start, end)
            tmp = BarAggregator(tf, self.cal)
            bars = [b for c in ones if (b := tmp.on_1m(c)) is not None]
        bars = bars[-need:]
        for b in bars:
            r.engine.on_candle(b)  # signals during warmup are discarded on purpose
        return len(bars)

    async def _refresh(self) -> None:
        async with get_session_factory()() as db:
            rows = await store.load_activations(db)
            seen: set[int] = set()
            for row in rows:
                a, v, acc = row.activation, row.version, row.account
                seen.add(a.id)
                ctx = await self._account_ctx(acc, db)
                r = self.runners.get(a.id)
                if r is None:
                    ins = await get_instrument(db, a.instrument_id)
                    if ins is None:
                        continue
                    doc = StrategyDocument.model_validate(v.dsl)
                    engine = StrategyEngine(
                        doc, a.instrument_id, self.cal, v.id, self._regime_provider(a.id)
                    )
                    limits = await self._limits(db, acc.id)
                    meta = InstrumentMeta(
                        instrument_id=ins.instrument_id,
                        symbol=ins.symbol,
                        segment=ins.segment,
                        lot_size=ins.lot_size,
                        tick_size=ins.tick_size,
                        underlying_symbol=ins.underlying_symbol,
                    )
                    ctx.sim.lot_size_of[ins.instrument_id] = ins.lot_size
                    ctx.sim.segment_of[ins.instrument_id] = ins.segment
                    from risk.engine import _product_for  # intraday/carry per segment

                    r = Runner(
                        activation_id=a.id,
                        version_id=v.id,
                        account_id=acc.id,
                        instrument_id=a.instrument_id,
                        engine=engine,
                        bars=BarAggregator(Timeframe(doc.timeframe), self.cal),
                        meta=meta,
                        product=_product_for(meta, True),
                        limits=limits,
                        risk=RiskEngine(limits),
                    )
                    prow = await store.open_position(db, acc.id, a.instrument_id)
                    if prow is not None and prow.quantity != 0:
                        engine.set_position(prow.quantity, prow.avg_price)
                    n = await self._warmup(r, db)
                    self.runners[a.id] = r
                    log.info(
                        "trader.activation_loaded",
                        activation=a.id,
                        symbol=ins.symbol,
                        timeframe=str(doc.timeframe),
                        warmup_bars=n,
                    )
                r.paused = a.status == ActivationStatus.PAUSED
                await self._load_regime(r, db)
                r.limits = await self._limits(db, acc.id)
                r.risk = RiskEngine(r.limits)
            # stopped activations: flatten if asked, then drop
            for aid in list(self.runners):
                if aid not in seen:
                    r = self.runners[aid]
                    ctx = self.accounts[r.account_id]
                    pos = ctx.book.position(r.instrument_id)
                    if not pos.is_flat and not r.flatten_requested:
                        r.flatten_requested = True
                        await self._square_off(r, "activation stopped", db)
                    elif pos.is_flat:
                        log.info("trader.activation_dropped", activation=aid)
                        del self.runners[aid]
            await db.commit()
        self._last_refresh = utcnow()

    def _regime_provider(self, activation_id: int) -> Any:
        """Closure read by the strategy engine's regime filters; backed by the DB rows the
        worker computes (daily at 09:05/16:10 IST, intraday every 15 min)."""

        def provider(ts: datetime) -> dict[str, Any]:
            r = self.runners.get(activation_id)
            if r is None or r.regime_daily is None:
                return {}
            out = r.regime_daily.as_dict()
            out["day_type"] = r.regime_intraday.day_type if r.regime_intraday else None
            return out

        return provider

    async def _load_regime(self, r: Runner, db: Any) -> None:
        now = utcnow()
        if r.regime_loaded_at and now - r.regime_loaded_at < timedelta(minutes=10):
            return
        r.regime_loaded_at = now
        try:
            r.regime_daily = await latest_daily(db, r.instrument_id)
            r.regime_intraday = await latest_intraday(
                db, r.instrument_id, now.astimezone(IST).date()
            )
        except Exception as exc:
            log.warning("trader.regime_load_failed", activation=r.activation_id, error=str(exc))

    def _regime_tag(self, r: Runner | None) -> dict[str, Any] | None:
        if r is None or r.regime_daily is None:
            return None
        d = r.regime_daily.as_dict()
        tag = {
            k: d.get(k)
            for k in (
                "date",
                "trend",
                "strength",
                "volatility",
                "structure",
                "adx",
                "vix",
                "regime_label",
            )
        }
        tag["day_type"] = r.regime_intraday.day_type if r.regime_intraday else None
        return tag

    async def _limits(self, db: Any, account_id: int) -> RiskLimits:
        from sqlalchemy import select

        from core.db.models import RiskLimit

        row = (
            await db.execute(
                select(RiskLimit).where(
                    RiskLimit.scope == RiskLimitScope.PAPER_ACCOUNT,
                    RiskLimit.scope_id == account_id,
                    RiskLimit.is_active.is_(True),
                )
            )
        ).scalar_one_or_none()
        return RiskLimits.model_validate(row.limits) if row else RiskLimits()

    # ------------------------------------------------------------------ signals -> orders
    def _account_state(self, ctx: AccountCtx) -> AccountState:
        book = ctx.book
        positions = tuple(book.open_positions())
        exposure = sum(
            (abs(p.quantity) * (p.last_price or p.avg_price) for p in positions), Decimal("0")
        )
        by_key: dict[str, Decimal] = {}
        for p in positions:
            r = next((x for x in self.runners.values() if x.instrument_id == p.instrument_id), None)
            key = r.meta.correlation_key if r else str(p.instrument_id)
            by_key[key] = by_key.get(key, Decimal("0")) + abs(p.quantity) * (
                p.last_price or p.avg_price
            )
        return AccountState(
            account_id=ctx.account.id,
            equity=book.equity,
            cash=book.cash,
            realized_today=ctx.realized_day,
            realized_week=ctx.realized_week,
            peak_equity=max(ctx.account.equity_hwm, book.equity),
            open_positions=positions,
            exposure=exposure,
            exposure_by_key=by_key,
        )

    async def _handle_signal(
        self, r: Runner, sig: Signal, db: Any, *, candle: Candle | None
    ) -> None:
        ctx = self.accounts[r.account_id]
        now = utcnow()
        quote = self.quotes.get(r.instrument_id)
        kill = await self.ks.any_active(r.account_id, r.version_id)
        if ctx.halted_reason and sig.kind == "entry":
            return
        if r.paused and sig.kind == "entry":
            return
        decision = r.risk.evaluate(
            sig,
            self._account_state(ctx),
            r.meta,
            quote,
            now=now,
            calendar=self.cal,
            kill_switch_active=bool(kill),
            mode=TradingMode.PAPER,
            product=r.product,
        )
        if not decision.allowed or decision.intent is None:
            log.info(
                "trader.signal_rejected",
                activation=r.activation_id,
                kind=sig.kind,
                reasons=list(decision.reasons),
            )
            return
        market = MarketState(ts=now, quote=quote, candle=candle)
        order = ctx.sim.submit(decision.intent, market)
        if order.order_id in ctx.row_ids:
            return  # idempotent repeat
        row_id = await store.insert_order(
            db,
            order,
            account_id=r.account_id,
            activation_id=r.activation_id,
            reason=f"{sig.kind}: {sig.reason}",
            bid=quote.bid if quote else None,
            ask=quote.ask if quote else None,
        )
        ctx.row_ids[order.order_id] = row_id
        ctx.events_synced[order.order_id] = len(order.events)
        ctx.order_runner[order.order_id] = r.activation_id
        if sig.kind == "entry":
            r.last_entry_reason = sig.reason
            r.entry_bar_count = 0
        else:
            r.last_exit_reason = f"{sig.kind}: {sig.reason}"
        log.info(
            "trader.order_submitted",
            activation=r.activation_id,
            side=order.intent.side.value,
            qty=order.intent.quantity,
            kind=sig.kind,
            reason=sig.reason,
        )
        # Market orders fill on the next market event; nudge with the current quote now.
        await self._process_fills(r.instrument_id, market, db)

    async def _square_off(self, r: Runner, why: str, db: Any) -> None:
        ctx = self.accounts[r.account_id]
        pos = ctx.book.position(r.instrument_id)
        if pos.is_flat:
            return
        quote = self.quotes.get(r.instrument_id)
        ref = quote.ltp if quote else pos.avg_price
        sig = Signal(
            strategy_version_id=r.version_id,
            instrument_id=r.instrument_id,
            ts=utcnow(),
            side=OrderSide.SELL if pos.quantity > 0 else OrderSide.BUY,
            kind="square_off",
            reason=why,
            reference_price=ref,
            suggested_quantity=abs(pos.quantity),
        )
        await self._handle_signal(r, sig, db, candle=None)

    # ------------------------------------------------------------------ fills
    async def _process_fills(self, instrument_id: int, market: MarketState, db: Any) -> None:
        for ctx in self.accounts.values():
            fills = ctx.sim.on_market(instrument_id, market)
            for fill in fills:
                order: Order = ctx.sim.orders[fill.order_id]
                closed = ctx.book.apply(order, fill)
                row_id = ctx.row_ids.get(order.order_id)
                aid = ctx.order_runner.get(order.order_id)
                r = self.runners.get(aid) if aid is not None else None
                if row_id is not None:
                    ctx.events_synced[order.order_id] = await store.sync_order(
                        db, row_id, order, events_from=ctx.events_synced.get(order.order_id, 0)
                    )
                    await store.add_fill_costs(db, row_id, fill, None)
                pos = ctx.book.position(instrument_id)
                await store.upsert_position(
                    db,
                    account_id=ctx.account.id,
                    activation_id=aid,
                    pos=pos,
                    product=order.intent.product,
                    now=fill.ts,
                )
                if r is not None:
                    r.engine.set_position(pos.quantity, None if pos.is_flat else pos.avg_price)
                log.info(
                    "trader.fill",
                    account=ctx.account.id,
                    side=order.intent.side.value,
                    qty=fill.quantity,
                    price=str(fill.price),
                    costs=str(fill.costs),
                )
                if closed is not None:
                    tid = await store.record_trade(
                        db,
                        closed,
                        account=ctx.account,
                        activation_id=aid,
                        entry_reason=r.last_entry_reason if r else None,
                        exit_reason=r.last_exit_reason if r else None,
                        regime=self._regime_tag(r),
                        bars_held=r.entry_bar_count if r else None,
                    )
                    ctx.realized_day += closed.net_pnl
                    ctx.realized_week += closed.net_pnl
                    log.info("trader.trade_closed", trade=tid, net=str(closed.net_pnl))
                    await self._check_loss_limits(ctx, r, db)
            # account row mirrors the book (cash after fills and costs, high-water mark)
            if fills:
                ctx.account.cash = ctx.book.cash
                ctx.account.equity_hwm = max(ctx.account.equity_hwm, ctx.book.equity)
                row = await db.get(PaperAccount, ctx.account.id)
                if row is not None:
                    row.cash = ctx.book.cash
                    row.equity_hwm = ctx.account.equity_hwm

    async def _check_loss_limits(self, ctx: AccountCtx, r: Runner | None, db: Any) -> None:
        limits = r.limits if r else RiskLimits()
        eq0 = ctx.account.initial_capital
        day_cap = -eq0 * Decimal(str(limits.max_daily_loss_pct)) / 100
        week_cap = -eq0 * Decimal(str(limits.max_weekly_loss_pct)) / 100
        why = None
        if ctx.realized_day <= day_cap:
            why = f"daily loss limit hit: {ctx.realized_day:.2f} <= {day_cap:.2f}"
        elif ctx.realized_week <= week_cap:
            why = f"weekly loss limit hit: {ctx.realized_week:.2f} <= {week_cap:.2f}"
        if why and ctx.halted_reason is None:
            ctx.halted_reason = why
            n = await store.pause_account(db, ctx.account.id, why)
            for x in self.runners.values():
                if x.account_id == ctx.account.id:
                    x.paused = True
                    await self._square_off(x, "loss limit: flattening", db)
            await self.redis.set(f"trader:halt:{ctx.account.id}", why.encode(), ex=24 * 3600)
            log.error("trader.halted", account=ctx.account.id, reason=why, paused=n)
            await self.notifier.send(
                f"Paper account {ctx.account.name}: {why}. Strategies paused.", level="critical"
            )

    # ------------------------------------------------------------------ market events
    async def _on_candle(self, c: Candle, db: Any) -> None:
        for r in list(self.runners.values()):
            if r.instrument_id != c.instrument_id or c.timeframe.value != "1m":
                continue
            closed = r.bars.on_1m(c)
            if closed is None:
                continue
            if not r.engine.state.position == "flat":
                r.entry_bar_count += 1
            signals = r.engine.on_candle(closed)
            rej = tuple(getattr(r.engine.state, "rejections", ()) or ())
            if rej != r.last_rejections:
                r.last_rejections = rej
                log.info("trader.engine_gate", activation=r.activation_id, rejections=list(rej))
            for sig in signals:
                await self._handle_signal(r, sig, db, candle=closed)

    async def _on_quote(self, q: Quote, db: Any) -> None:
        self.quotes[q.instrument_id] = q
        market = MarketState(ts=q.ts, quote=q)
        for ctx in self.accounts.values():
            ctx.book.mark(q.instrument_id, q.ltp)
        await self._process_fills(q.instrument_id, market, db)

    async def _time_rules(self, db: Any) -> None:
        now = utcnow()
        for r in list(self.runners.values()):
            closed = r.bars.maybe_close(now)
            if closed is not None:
                for sig in r.engine.on_candle(closed):
                    await self._handle_signal(r, sig, db, candle=closed)
            for sig in r.engine.on_time(now):
                await self._handle_signal(r, sig, db, candle=None)
            if r.flatten_requested:
                await self._square_off(r, "flatten requested", db)
            kill = await self.ks.any_active(r.account_id, r.version_id)
            if kill:
                st = await self.ks.status(kill[0])
                if st and "[flatten]" in str(st.get("reason", "")):
                    await self._square_off(r, f"kill switch {kill[0]}", db)

    async def _snapshot(self, db: Any) -> None:
        now = utcnow()
        if self._last_snapshot and now - self._last_snapshot < SNAPSHOT_EVERY:
            return
        self._last_snapshot = now
        for ctx in self.accounts.values():
            st = self._account_state(ctx)
            for p in st.open_positions:
                if p.last_price is not None:
                    await store.mark_position(db, ctx.account.id, p.instrument_id, p.last_price)
            await store.snapshot(
                db,
                ctx.account,
                equity=st.equity,
                cash=st.cash,
                exposure=st.exposure,
                realized_day=ctx.realized_day,
                unrealized=ctx.book.unrealized,
                open_positions=st.open_count,
            )
        health = {
            "updated_at": now.isoformat(),
            "activations": [
                {
                    "id": r.activation_id,
                    "instrument_id": r.instrument_id,
                    "paused": r.paused,
                    "position": r.engine.state.position,
                    "qty": r.engine.state.quantity,
                }
                for r in self.runners.values()
            ],
            "accounts": [
                {
                    "id": c.account.id,
                    "equity": str(c.book.equity),
                    "cash": str(c.book.cash),
                    "realized_day": str(c.realized_day),
                    "halted": c.halted_reason,
                }
                for c in self.accounts.values()
            ],
        }
        await self.redis.set("trader:health", orjson.dumps(health), ex=120)

    # ------------------------------------------------------------------ loops
    async def _market_loop(self) -> None:
        pubsub = self.redis.pubsub()
        await pubsub.subscribe("market.tick", "market.candle")
        try:
            async for msg in pubsub.listen():
                if self._stop.is_set():
                    break
                if msg.get("type") != "message":
                    continue
                data = orjson.loads(msg["data"])
                async with get_session_factory()() as db:
                    try:
                        if msg["channel"] == b"market.candle":
                            await self._on_candle(Candle.model_validate(data), db)
                        else:
                            await self._on_quote(Quote.model_validate(data), db)
                        await db.commit()
                    except Exception as exc:
                        await db.rollback()
                        log.error("trader.event_error", error=str(exc), channel=str(msg["channel"]))
        finally:
            with contextlib.suppress(Exception):
                await pubsub.unsubscribe()
                await pubsub.aclose()

    async def _housekeeping(self) -> None:
        while not self._stop.is_set():
            try:
                if self._last_refresh is None or utcnow() - self._last_refresh >= REFRESH_EVERY:
                    await self._refresh()
                async with get_session_factory()() as db:
                    await self._time_rules(db)
                    await self._snapshot(db)
                    await db.commit()
            except Exception as exc:
                log.error("trader.housekeeping_error", error=str(exc))
            await asyncio.sleep(2)

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (os_signal.SIGINT, os_signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self._stop.set)
            except NotImplementedError:  # Windows: the proactor loop has no signal handlers
                os_signal.signal(sig, lambda *_: loop.call_soon_threadsafe(self._stop.set))
        async with get_session_factory()() as db:
            n = await store.cancel_stale_open_orders(db, "trader restart")
            await db.commit()
        log.info("trader.started", stale_orders_cancelled=n)
        await self._refresh()
        tasks = [
            asyncio.create_task(self._market_loop()),
            asyncio.create_task(self._housekeeping()),
        ]
        await self._stop.wait()
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await self.redis.aclose()
        log.info("trader.stopped")


def main() -> None:
    s = get_settings()
    configure_logging(s.log_level, s.log_json)
    asyncio.run(Trader(s).run())


if __name__ == "__main__":
    main()
