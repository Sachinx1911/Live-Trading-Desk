"""Pre-trade risk engine. Entries must pass every check; reducing orders always pass but
are sized to the open position so an exit can never flip a position."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from core.calendar import ExchangeCalendar
from core.models import (
    OrderIntent,
    OrderSide,
    OrderType,
    ProductType,
    Quote,
    Segment,
    Signal,
    TradingMode,
)
from core.time import ensure_utc
from risk.limits import AccountState, InstrumentMeta, RiskLimits
from risk.owner_rules import MarketContext, evaluate_owner_rules
from risk.sizing import SizingResult, size_order

REDUCING_KINDS = frozenset({"exit", "stop", "target", "square_off"})


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    reasons: tuple[str, ...]
    intent: OrderIntent | None
    sizing: SizingResult | None
    checks: tuple[str, ...] = field(default_factory=tuple)  # checks that ran, for the journal


def _price(signal: Signal, quote: Quote | None) -> Decimal:
    if quote is not None:
        if signal.side == OrderSide.BUY and quote.ask is not None:
            return quote.ask
        if signal.side == OrderSide.SELL and quote.bid is not None:
            return quote.bid
        return quote.ltp
    return signal.reference_price


def _product_for(instrument: InstrumentMeta, intraday: bool) -> ProductType:
    if instrument.segment in (Segment.FUTURES, Segment.OPTIONS):
        return ProductType.INTRADAY if intraday else ProductType.CARRY
    return ProductType.INTRADAY if intraday else ProductType.DELIVERY


class RiskEngine:
    def __init__(self, limits: RiskLimits) -> None:
        self.limits = limits

    def evaluate(
        self,
        signal: Signal,
        account: AccountState,
        instrument: InstrumentMeta,
        quote: Quote | None,
        *,
        now: datetime,
        calendar: ExchangeCalendar,
        kill_switch_active: bool,
        events_today: list[str] | None = None,
        mode: TradingMode = TradingMode.PAPER,
        intraday: bool = True,
        product: ProductType | None = None,
        market: MarketContext | None = None,
    ) -> RiskDecision:
        now = ensure_utc(now)
        price = _price(signal, quote)
        product = product or _product_for(instrument, intraday)
        if signal.kind in REDUCING_KINDS:
            return self._reducing(signal, account, product, mode)
        return self._entry(
            signal,
            account,
            instrument,
            quote,
            price,
            now,
            calendar,
            kill_switch_active,
            events_today or [],
            mode,
            product,
            market,
        )

    # -- reducing orders ---------------------------------------------------------------
    def _reducing(
        self, signal: Signal, account: AccountState, product: ProductType, mode: TradingMode
    ) -> RiskDecision:
        pos = account.position_for(signal.instrument_id)
        if pos is None:
            return RiskDecision(False, ("no open position to reduce",), None, None, ("position",))
        closing_side = OrderSide.SELL if pos.quantity > 0 else OrderSide.BUY
        if signal.side != closing_side:
            return RiskDecision(
                False,
                (f"{signal.kind} side {signal.side} does not reduce position",),
                None,
                None,
                ("position",),
            )
        qty = abs(pos.quantity)
        if signal.suggested_quantity:
            qty = min(qty, signal.suggested_quantity)
        sizing = SizingResult(qty, 0, Decimal(0), None, Decimal(0), "reduce_to_position")
        intent = self._intent(signal, account, mode, product, qty, OrderType.MARKET)
        return RiskDecision(True, (), intent, sizing, ("position",))

    # -- entries -----------------------------------------------------------------------
    def _entry(
        self,
        signal: Signal,
        account: AccountState,
        instrument: InstrumentMeta,
        quote: Quote | None,
        price: Decimal,
        now: datetime,
        calendar: ExchangeCalendar,
        kill_switch_active: bool,
        events_today: list[str],
        mode: TradingMode,
        product: ProductType,
        market: MarketContext | None,
    ) -> RiskDecision:
        lim = self.limits
        reasons: list[str] = []
        checks: list[str] = []

        def fail(check: str, msg: str) -> None:
            checks.append(check)
            reasons.append(msg)

        def ok(check: str) -> None:
            checks.append(check)

        # 1 kill switch
        (fail("kill_switch", "kill switch active") if kill_switch_active else ok("kill_switch"))

        # 2 session window (exchange local time)
        local = now.astimezone(calendar.tz)
        session = calendar.session_for(local.date())
        if session is None:
            fail("session", "market closed today")
        elif not (lim.trade_start <= local.time() < lim.no_new_entries_after):
            fail(
                "session",
                f"outside entry window {lim.trade_start:%H:%M}-{lim.no_new_entries_after:%H:%M}",
            )
        else:
            ok("session")

        # 3/4 daily and weekly loss
        daily_cap = account.equity * Decimal(str(lim.max_daily_loss_pct)) / 100
        weekly_cap = account.equity * Decimal(str(lim.max_weekly_loss_pct)) / 100
        (
            fail("daily_loss", "daily loss limit breached")
            if -account.realized_today >= daily_cap
            else ok("daily_loss")
        )
        (
            fail("weekly_loss", "weekly loss limit breached")
            if -account.realized_week >= weekly_cap
            else ok("weekly_loss")
        )

        # 5 open positions
        existing = account.position_for(signal.instrument_id)
        if existing is None and account.open_count >= lim.max_open_positions:
            fail("max_positions", f"max open positions {lim.max_open_positions} reached")
        elif existing is not None and (existing.quantity > 0) != (signal.side == OrderSide.BUY):
            fail("max_positions", "entry would offset an existing position; use an exit signal")
        else:
            ok("max_positions")

        # 6 shorts
        (
            fail("allow_short", "short entries disabled")
            if signal.side == OrderSide.SELL and not lim.allow_short
            else ok("allow_short")
        )

        # 7 product
        (
            fail("product", f"product {product} not allowed")
            if product not in lim.allowed_products
            else ok("product")
        )

        # 8 event block
        (
            fail("event_block", f"high-impact event today: {', '.join(events_today)}")
            if lim.event_block and events_today
            else ok("event_block")
        )

        # sizing (needed by the remaining checks)
        sizing = size_order(signal, lim, account, instrument, price)
        if sizing.quantity <= 0:
            fail("sizing", f"size is zero ({sizing.reason})")
        else:
            ok("sizing")

        # 9 exposure after trade
        exposure_cap = account.equity * Decimal(str(lim.max_exposure_pct)) / 100
        (
            fail("exposure", "exposure cap exceeded")
            if account.exposure + sizing.notional > exposure_cap
            else ok("exposure")
        )

        # 10 correlated exposure
        corr_cap = account.equity * Decimal(str(lim.max_correlated_exposure_pct)) / 100
        bucket = account.exposure_by_key.get(instrument.correlation_key, Decimal(0))
        (
            fail(
                "correlated_exposure",
                f"correlated exposure cap exceeded for {instrument.correlation_key}",
            )
            if bucket + sizing.notional > corr_cap
            else ok("correlated_exposure")
        )

        # 11 lots cap
        (
            fail("lots_cap", f"lots {sizing.lots} exceed max {lim.max_lots_per_order}")
            if sizing.lots > lim.max_lots_per_order
            else ok("lots_cap")
        )

        # 12 freeze quantity
        if (
            lim.freeze_quantity_check
            and instrument.freeze_quantity
            and sizing.quantity > instrument.freeze_quantity
        ):
            fail(
                "freeze_quantity",
                f"quantity {sizing.quantity} exceeds freeze quantity {instrument.freeze_quantity}",
            )
        else:
            ok("freeze_quantity")

        # 13 per-trade risk cap
        risk_cap = account.equity * Decimal(str(lim.max_risk_per_trade_pct)) / 100
        if sizing.risk_per_unit is None:
            ok(
                "risk_per_trade"
            )  # no stop: sizing fell back to suggested/one lot (warned by DSL validation)
        elif sizing.risk_amount > risk_cap:
            fail("risk_per_trade", f"risk {sizing.risk_amount} exceeds cap {risk_cap:.2f}")
        else:
            ok("risk_per_trade")

        # 14+ owner trading rules (risk.owner_rules): named hard blocks, e.g. pcr_guard
        for code, outcome in evaluate_owner_rules(signal, instrument, market, lim):
            if outcome.status == "block":
                fail(code, outcome.message)
            elif outcome.status == "pass":
                ok(code)
            elif outcome.status == "skipped":
                ok(f"{code}:skipped")

        if reasons:
            return RiskDecision(False, tuple(reasons), None, sizing, tuple(checks))
        intent = self._intent(signal, account, mode, product, sizing.quantity, OrderType.MARKET)
        return RiskDecision(True, (), intent, sizing, tuple(checks))

    @staticmethod
    def _intent(
        signal: Signal,
        account: AccountState,
        mode: TradingMode,
        product: ProductType,
        qty: int,
        order_type: OrderType,
    ) -> OrderIntent:
        return OrderIntent(
            signal_id=signal.signal_id,
            strategy_version_id=signal.strategy_version_id,
            account_id=account.account_id,
            mode=mode,
            instrument_id=signal.instrument_id,
            side=signal.side,
            order_type=order_type,
            product=product,
            quantity=qty,
            idempotency_key=OrderIntent.make_key(signal.strategy_version_id, signal.signal_id),
        )
