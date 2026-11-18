"""Persistence for the paper runner. Everything the simulator does in memory is mirrored
to paper_* tables so the UI and the AI reviewer see it (ADR-008)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import (
    JournalEntry,
    PaperAccount,
    PaperOrder,
    PaperOrderEvent,
    PaperPosition,
    PaperTrade,
    PerformanceDaily,
    PortfolioSnapshot,
    StrategyActivation,
    StrategyVersion,
)
from core.db.models._enums import ActivationStatus
from core.models import Fill, OrderStatus, Position, TradingMode
from core.time import IST, utcnow
from execution.orders import Order
from execution.simulator.book import ClosedTrade


@dataclass
class ActivationRow:
    activation: StrategyActivation
    version: StrategyVersion
    account: PaperAccount


async def load_activations(db: AsyncSession) -> list[ActivationRow]:
    q = (
        select(StrategyActivation, StrategyVersion, PaperAccount)
        .join(StrategyVersion, StrategyVersion.id == StrategyActivation.version_id)
        .join(PaperAccount, PaperAccount.id == StrategyActivation.paper_account_id)
        .where(
            StrategyActivation.trading_mode == TradingMode.PAPER,
            StrategyActivation.status != ActivationStatus.STOPPED,
            PaperAccount.is_active.is_(True),
        )
    )
    return [ActivationRow(a, v, acc) for a, v, acc in (await db.execute(q)).all()]


async def recently_stopped(db: AsyncSession, since: datetime) -> list[StrategyActivation]:
    q = select(StrategyActivation).where(
        StrategyActivation.trading_mode == TradingMode.PAPER,
        StrategyActivation.status == ActivationStatus.STOPPED,
        StrategyActivation.stopped_at >= since,
    )
    return list((await db.execute(q)).scalars().all())


async def open_position(
    db: AsyncSession, account_id: int, instrument_id: int
) -> PaperPosition | None:
    q = select(PaperPosition).where(
        PaperPosition.paper_account_id == account_id,
        PaperPosition.instrument_id == instrument_id,
        PaperPosition.closed_at.is_(None),
    )
    return (await db.execute(q)).scalar_one_or_none()


async def cancel_stale_open_orders(db: AsyncSession, reason: str) -> int:
    """On startup the in-memory simulator is empty, so DB orders still open are orphans."""
    q = select(PaperOrder).where(
        PaperOrder.status.in_(
            [OrderStatus.SUBMITTED, OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED]
        )
    )
    n = 0
    now = utcnow()
    for o in (await db.execute(q)).scalars():
        db.add(
            PaperOrderEvent(
                order_id=o.id,
                from_status=o.status,
                to_status=OrderStatus.CANCELLED,
                reason=reason,
                source="trader",
                ts=now,
            )
        )
        o.status = OrderStatus.CANCELLED
        o.reason = reason
        o.updated_at = now
        n += 1
    return n


async def insert_order(
    db: AsyncSession,
    order: Order,
    *,
    account_id: int,
    activation_id: int | None,
    reason: str,
    bid: Decimal | None,
    ask: Decimal | None,
) -> int:
    i = order.intent
    row = PaperOrder(
        paper_account_id=account_id,
        activation_id=activation_id,
        instrument_id=i.instrument_id,
        signal_id=i.signal_id,
        idempotency_key=i.idempotency_key,
        side=i.side,
        order_type=i.order_type,
        product=i.product,
        quantity=i.quantity,
        filled_qty=0,
        limit_price=i.limit_price,
        trigger_price=i.trigger_price,
        avg_fill_price=None,
        status=order.status,
        reason=reason,
        costs=Decimal("0"),
        cost_breakdown=None,
        bid_at_place=bid,
        ask_at_place=ask,
        submitted_at=order.created_at,
        updated_at=order.updated_at,
    )
    db.add(row)
    await db.flush()
    for ev in order.events:
        db.add(
            PaperOrderEvent(
                order_id=row.id,
                from_status=ev.from_status,
                to_status=ev.to_status,
                fill_qty=ev.fill_qty,
                fill_px=ev.fill_px,
                reason=ev.reason,
                source=ev.source,
                ts=ev.ts,
            )
        )
    return row.id


async def sync_order(db: AsyncSession, row_id: int, order: Order, *, events_from: int) -> int:
    """Mirror the in-memory order onto its row; append events not yet stored."""
    row = await db.get(PaperOrder, row_id)
    if row is None:
        return events_from
    row.status = order.status
    row.filled_qty = order.filled_qty
    row.avg_fill_price = order.avg_fill_price
    row.updated_at = order.updated_at
    for ev in order.events[events_from:]:
        db.add(
            PaperOrderEvent(
                order_id=row.id,
                from_status=ev.from_status,
                to_status=ev.to_status,
                fill_qty=ev.fill_qty,
                fill_px=ev.fill_px,
                reason=ev.reason,
                source=ev.source,
                ts=ev.ts,
            )
        )
    return len(order.events)


async def add_fill_costs(
    db: AsyncSession, row_id: int, fill: Fill, breakdown: dict[str, Any] | None
) -> None:
    row = await db.get(PaperOrder, row_id)
    if row is None:
        return
    row.costs = (row.costs or Decimal("0")) + fill.costs
    if breakdown:
        prev = row.cost_breakdown or {}
        row.cost_breakdown = {
            k: str(Decimal(str(prev.get(k, "0"))) + Decimal(str(v))) for k, v in breakdown.items()
        }


async def upsert_position(
    db: AsyncSession,
    *,
    account_id: int,
    activation_id: int | None,
    pos: Position,
    product: Any,
    now: datetime,
) -> None:
    row = await open_position(db, account_id, pos.instrument_id)
    if pos.quantity == 0:
        if row is not None:
            row.quantity = 0
            row.realized_pnl = pos.realized_pnl
            row.unrealized_pnl = Decimal("0")
            row.last_price = pos.last_price
            row.closed_at = now
        return
    if row is None:
        row = PaperPosition(
            paper_account_id=account_id,
            instrument_id=pos.instrument_id,
            product=product,
            activation_id=activation_id,
            quantity=pos.quantity,
            avg_price=pos.avg_price,
            realized_pnl=pos.realized_pnl,
            unrealized_pnl=pos.unrealized_pnl,
            last_price=pos.last_price,
            opened_at=now,
        )
        db.add(row)
    else:
        row.quantity = pos.quantity
        row.avg_price = pos.avg_price
        row.realized_pnl = pos.realized_pnl
        row.unrealized_pnl = pos.unrealized_pnl
        row.last_price = pos.last_price


async def mark_position(
    db: AsyncSession, account_id: int, instrument_id: int, last: Decimal
) -> None:
    row = await open_position(db, account_id, instrument_id)
    if row is not None and row.quantity != 0:
        row.last_price = last
        row.unrealized_pnl = (last - row.avg_price) * row.quantity


async def record_trade(
    db: AsyncSession,
    ct: ClosedTrade,
    *,
    account: PaperAccount,
    activation_id: int | None,
    entry_reason: str | None,
    exit_reason: str | None,
    regime: dict[str, Any] | None,
    bars_held: int | None,
) -> int:
    t = PaperTrade(
        paper_account_id=account.id,
        activation_id=activation_id,
        strategy_version_id=ct.strategy_version_id,
        instrument_id=ct.instrument_id,
        side=ct.side,
        quantity=ct.quantity,
        entry_at=ct.entry_at,
        entry_price=ct.entry_price,
        exit_at=ct.exit_at,
        exit_price=ct.exit_price,
        gross_pnl=ct.gross_pnl,
        costs=ct.costs,
        net_pnl=ct.net_pnl,
        entry_reason=entry_reason,
        exit_reason=exit_reason,
        regime=regime,
        bars_held=bars_held,
    )
    db.add(t)
    await db.flush()
    db.add(
        JournalEntry(
            user_id=account.user_id,
            mode=TradingMode.PAPER,
            trade_ref_table="paper_trades",
            trade_ref_id=t.id,
            strategy_version_id=ct.strategy_version_id,
            entry_reason=entry_reason,
            exit_reason=exit_reason,
            market_conditions=regime,
            pnl=ct.net_pnl,
            risk_amount=None,
            user_notes=None,
            tags=["paper", "auto"],
        )
    )
    day = ct.exit_at.astimezone(IST).date()
    pd = await db.get(
        PerformanceDaily, {"account_id": account.id, "mode": TradingMode.PAPER, "day": day}
    )
    if pd is None:
        pd = PerformanceDaily(
            user_id=account.user_id,
            mode=TradingMode.PAPER,
            account_id=account.id,
            day=day,
            pnl=Decimal("0"),
            trades=0,
            wins=0,
            losses=0,
            fees=Decimal("0"),
            max_dd=Decimal("0"),
        )
        db.add(pd)
    pd.pnl += ct.net_pnl
    pd.trades += 1
    pd.wins += 1 if ct.net_pnl > 0 else 0
    pd.losses += 1 if ct.net_pnl < 0 else 0
    pd.fees += ct.costs
    return t.id


async def realized_since(db: AsyncSession, account_id: int, since: datetime) -> Decimal:
    q = select(func.coalesce(func.sum(PaperTrade.net_pnl), 0)).where(
        PaperTrade.paper_account_id == account_id, PaperTrade.exit_at >= since
    )
    return Decimal((await db.execute(q)).scalar_one())


def day_start_utc(d: date) -> datetime:
    return datetime.combine(d, datetime.min.time(), tzinfo=IST).astimezone(IST)


def week_start_utc(d: date) -> datetime:
    return day_start_utc(d - timedelta(days=d.weekday()))


async def snapshot(
    db: AsyncSession,
    account: PaperAccount,
    *,
    equity: Decimal,
    cash: Decimal,
    exposure: Decimal,
    realized_day: Decimal,
    unrealized: Decimal,
    open_positions: int,
) -> None:
    db.add(
        PortfolioSnapshot(
            user_id=account.user_id,
            mode=TradingMode.PAPER,
            account_id=account.id,
            ts=utcnow(),
            equity=equity,
            cash=cash,
            exposure=exposure,
            realized_day=realized_day,
            unrealized=unrealized,
            open_positions=open_positions,
        )
    )


async def pause_account(db: AsyncSession, account_id: int, reason: str) -> int:
    q = select(StrategyActivation).where(
        StrategyActivation.paper_account_id == account_id,
        StrategyActivation.status == ActivationStatus.ACTIVE,
    )
    n = 0
    for a in (await db.execute(q)).scalars():
        a.status = ActivationStatus.PAUSED
        a.stop_reason = reason
        n += 1
    return n
