"""Execution simulator shared by backtest, replay and paper trading (ADR-002).

Rules that keep results honest and reproducible:
- An order never fills on the event that created it; fills come from the NEXT market event.
- Market orders fill at the opposite side of the book (ask for buys, bid for sells) when
  depth is present, else at LTP moved by the slippage model.
- Quantity above the visible top-of-book fills partially; the rest waits for later events
  (bounded by `max_partial_events`, after which the remainder fills with slippage).
- Stop orders trigger on the reference price, then execute as market / limit.
- Costs come from the cost model for every fill.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from core.calendar import ExchangeCalendar
from core.models import Candle, Fill, OrderIntent, OrderSide, OrderStatus, OrderType, Quote, Segment
from execution.costs import CostModel
from execution.orders import IdempotencyIndex, Order, transition
from execution.simulator.slippage import FixedBpsSlippage, SlippageModel

SOURCE = "simulator"


@dataclass(frozen=True)
class MarketState:
    ts: datetime
    quote: Quote | None = None
    candle: Candle | None = None

    @property
    def reference(self) -> Decimal | None:
        if self.quote is not None:
            return self.quote.ltp
        if self.candle is not None:
            return self.candle.close
        return None

    def book_side(self, side: OrderSide) -> tuple[Decimal | None, int | None]:
        """(price, available qty) the taker would hit: ask for buys, bid for sells."""
        if self.quote is None:
            return None, None
        if side == OrderSide.BUY:
            return self.quote.ask, self.quote.ask_qty
        return self.quote.bid, self.quote.bid_qty


class ExecutionSimulator:
    def __init__(
        self,
        cost_model: CostModel | None = None,
        slippage: SlippageModel | None = None,
        *,
        seed: int = 42,
        calendar: ExchangeCalendar | None = None,
        max_partial_events: int = 3,
        lot_size_of: dict[int, int] | None = None,
        segment_of: dict[int, Segment] | None = None,
    ) -> None:
        self.cost_model = cost_model or CostModel()
        self.slippage: SlippageModel = slippage or FixedBpsSlippage(5)
        self.seed = seed
        self.calendar = calendar
        self.max_partial_events = max_partial_events
        self.lot_size_of = lot_size_of or {}
        self.segment_of = segment_of or {}
        self.orders: dict[UUID, Order] = {}
        self.idempotency = IdempotencyIndex()
        self._partials: dict[UUID, int] = {}
        self._triggered: set[UUID] = set()

    # ------------------------------------------------------------------ order entry
    def submit(self, intent: OrderIntent, market: MarketState) -> Order:
        existing = self.idempotency.get(intent.idempotency_key)
        if existing is not None:
            return self.orders[existing]
        if self.calendar is not None and not self.calendar.is_open(market.ts):
            order = Order(intent=intent, created_at=market.ts, updated_at=market.ts)
            self.orders[order.order_id] = order
            self.idempotency.register(intent.idempotency_key, order.order_id)
            transition(
                order, OrderStatus.REJECTED, reason="market closed", source=SOURCE, ts=market.ts
            )
            return order
        order = Order(intent=intent, created_at=market.ts, updated_at=market.ts)
        self.orders[order.order_id] = order
        self.idempotency.register(intent.idempotency_key, order.order_id)
        transition(
            order,
            OrderStatus.SUBMITTED,
            reason="accepted by simulator",
            source=SOURCE,
            ts=market.ts,
        )
        transition(order, OrderStatus.OPEN, reason="working", source=SOURCE, ts=market.ts)
        return order

    def cancel(self, order_id: UUID, reason: str, ts: datetime | None = None) -> Order:
        order = self.orders[order_id]
        if order.is_open:
            transition(order, OrderStatus.CANCELLED, reason=reason, source=SOURCE, ts=ts)
        return order

    def open_orders(self, instrument_id: int | None = None) -> list[Order]:
        return [
            o
            for o in self.orders.values()
            if o.is_open and (instrument_id is None or o.instrument_id == instrument_id)
        ]

    # ------------------------------------------------------------------ matching
    def on_market(self, instrument_id: int, market: MarketState) -> list[Fill]:
        fills: list[Fill] = []
        ref = market.reference
        if ref is None:
            return fills
        for order in self.open_orders(instrument_id):
            if order.created_at >= market.ts:
                continue  # never fill on the creating event
            fill = self._try_fill(order, market, ref)
            if fill is not None:
                fills.append(fill)
        return fills

    def _try_fill(self, order: Order, market: MarketState, ref: Decimal) -> Fill | None:
        intent = order.intent
        side = intent.side
        otype = intent.order_type

        if (
            otype in (OrderType.STOP, OrderType.STOP_LIMIT)
            and order.order_id not in self._triggered
        ):
            trig = intent.trigger_price
            if trig is None:
                return None
            hit = ref >= trig if side == OrderSide.BUY else ref <= trig
            if not hit:
                return None
            self._triggered.add(order.order_id)

        book_px, book_qty = market.book_side(side)
        if otype in (OrderType.MARKET, OrderType.STOP):
            px = book_px if book_px is not None else self._slipped(ref, order)
        else:  # LIMIT / STOP_LIMIT
            limit = intent.limit_price
            if limit is None:
                return None
            touch = book_px if book_px is not None else ref
            crossed = touch <= limit if side == OrderSide.BUY else touch >= limit
            if not crossed:
                return None
            px = touch  # price improvement when the book is better than the limit

        qty = order.remaining_qty
        n = self._partials.get(order.order_id, 0)
        if book_qty is not None and book_qty > 0 and book_qty < qty and n < self.max_partial_events:
            qty = book_qty
        if qty <= 0:
            return None
        return self._fill(order, qty, px, market.ts)

    def _slipped(self, ref: Decimal, order: Order) -> Decimal:
        lot = self.lot_size_of.get(order.intent.instrument_id, 1)
        return self.slippage.apply(ref, order.intent.side, order.remaining_qty, lot)

    def _fill(self, order: Order, qty: int, px: Decimal, ts: datetime) -> Fill:
        intent = order.intent
        seg = self.segment_of.get(intent.instrument_id, Segment.EQUITY)
        lot = self.lot_size_of.get(intent.instrument_id, 1)
        costs = self.cost_model.compute(
            segment=seg,
            product=intent.product,
            side=intent.side,
            quantity=qty,
            price=px,
            lots=max(1, qty // max(1, lot)),
            on=ts.date(),
        ).total
        partial = qty < order.remaining_qty
        to = OrderStatus.PARTIALLY_FILLED if partial else OrderStatus.FILLED
        transition(order, to, reason="fill", source=SOURCE, ts=ts, fill=(qty, px))
        if partial:
            self._partials[order.order_id] = self._partials.get(order.order_id, 0) + 1
        return Fill(
            order_id=order.order_id, ts=ts, quantity=qty, price=px, costs=costs, is_partial=partial
        )
