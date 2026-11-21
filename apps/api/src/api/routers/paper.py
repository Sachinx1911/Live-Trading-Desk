"""Paper trading: accounts, orders, positions, trades, strategy activations (ADR-008)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from api.audit import audit
from api.deps import DB, State, User
from core.db.models import (
    Instrument as InstrumentRow,
)
from core.db.models import (
    PaperAccount,
    PaperOrder,
    PaperOrderEvent,
    PaperPosition,
    PaperTrade,
    StrategyActivation,
    StrategyVersion,
)
from core.db.models._enums import ActivationStatus, StrategyVersionStatus
from core.models import OrderSide, OrderStatus, OrderType, ProductType, TradingMode
from core.services.paper import stop_activation as stop_paper_activation
from core.time import utcnow

router = APIRouter(prefix="/paper", tags=["paper"])


# ---------------------------------------------------------------- schemas
class AccountIn(BaseModel):
    name: str = Field(min_length=1, max_length=80, default="Paper account")
    initial_capital: Decimal | None = Field(default=None, gt=0)


class AccountOut(BaseModel):
    id: int
    name: str
    currency: str
    initial_capital: Decimal
    cash: Decimal
    equity: Decimal
    equity_hwm: Decimal
    unrealized_pnl: Decimal
    realized_pnl_total: Decimal
    open_positions: int
    is_active: bool
    reset_at: datetime | None
    created_at: datetime


class OrderOut(BaseModel):
    id: int
    paper_account_id: int
    activation_id: int | None
    instrument_id: int
    symbol: str | None = None
    side: OrderSide
    order_type: OrderType
    product: ProductType
    quantity: int
    filled_qty: int
    limit_price: Decimal | None
    trigger_price: Decimal | None
    avg_fill_price: Decimal | None
    status: OrderStatus
    reason: str | None
    costs: Decimal
    cost_breakdown: dict[str, Any] | None
    bid_at_place: Decimal | None
    ask_at_place: Decimal | None
    submitted_at: datetime
    updated_at: datetime


class OrderEventOut(BaseModel):
    id: int
    from_status: OrderStatus
    to_status: OrderStatus
    fill_qty: int | None
    fill_px: Decimal | None
    reason: str | None
    source: str
    ts: datetime


class PositionOut(BaseModel):
    id: int
    instrument_id: int
    symbol: str | None = None
    product: ProductType
    activation_id: int | None
    quantity: int
    avg_price: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    last_price: Decimal | None
    opened_at: datetime
    closed_at: datetime | None


class TradeOut(BaseModel):
    id: int
    activation_id: int | None
    strategy_version_id: int | None
    instrument_id: int
    symbol: str | None = None
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


class ActivationIn(BaseModel):
    version_id: int
    instrument_id: int
    params_override: dict[str, Any] = {}


class ActivationOut(BaseModel):
    id: int
    version_id: int
    strategy_id: int
    strategy_name: str
    version_no: int
    trading_mode: TradingMode
    paper_account_id: int | None
    instrument_id: int
    symbol: str | None
    status: ActivationStatus
    activated_at: datetime
    stopped_at: datetime | None
    stop_reason: str | None


# ---------------------------------------------------------------- helpers
async def _account(db: DB, user: User, account_id: int) -> PaperAccount:
    a = await db.get(PaperAccount, account_id)
    if a is None or a.user_id != user.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "paper account not found")
    return a


async def _symbols(db: DB, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    rows = await db.execute(
        select(InstrumentRow.id, InstrumentRow.symbol).where(InstrumentRow.id.in_(ids))
    )
    return {i: s for i, s in rows.all()}


async def _aout(db: DB, a: PaperAccount) -> AccountOut:
    pos = (
        (
            await db.execute(
                select(PaperPosition).where(
                    PaperPosition.paper_account_id == a.id, PaperPosition.closed_at.is_(None)
                )
            )
        )
        .scalars()
        .all()
    )
    unreal = sum((p.unrealized_pnl for p in pos), Decimal("0"))
    realized_total = (
        await db.execute(
            select(func.coalesce(func.sum(PaperTrade.net_pnl), 0)).where(
                PaperTrade.paper_account_id == a.id
            )
        )
    ).scalar_one()
    # Equity = cash + market value of open positions; cash already reflects fills and costs.
    mv = sum((p.quantity * (p.last_price or p.avg_price) for p in pos), Decimal("0"))
    return AccountOut(
        id=a.id,
        name=a.name,
        currency=a.currency,
        initial_capital=a.initial_capital,
        cash=a.cash,
        equity=a.cash + mv,
        equity_hwm=a.equity_hwm,
        unrealized_pnl=unreal,
        realized_pnl_total=Decimal(realized_total),
        open_positions=sum(1 for p in pos if p.quantity != 0),
        is_active=a.is_active,
        reset_at=a.reset_at,
        created_at=a.created_at,
    )


def _oout(o: PaperOrder, sym: dict[int, str]) -> OrderOut:
    return OrderOut(
        id=o.id,
        paper_account_id=o.paper_account_id,
        activation_id=o.activation_id,
        instrument_id=o.instrument_id,
        symbol=sym.get(o.instrument_id),
        side=o.side,
        order_type=o.order_type,
        product=o.product,
        quantity=o.quantity,
        filled_qty=o.filled_qty,
        limit_price=o.limit_price,
        trigger_price=o.trigger_price,
        avg_fill_price=o.avg_fill_price,
        status=o.status,
        reason=o.reason,
        costs=o.costs,
        cost_breakdown=o.cost_breakdown,
        bid_at_place=o.bid_at_place,
        ask_at_place=o.ask_at_place,
        submitted_at=o.submitted_at,
        updated_at=o.updated_at,
    )


def _pout(p: PaperPosition, sym: dict[int, str]) -> PositionOut:
    return PositionOut(
        id=p.id,
        instrument_id=p.instrument_id,
        symbol=sym.get(p.instrument_id),
        product=p.product,
        activation_id=p.activation_id,
        quantity=p.quantity,
        avg_price=p.avg_price,
        realized_pnl=p.realized_pnl,
        unrealized_pnl=p.unrealized_pnl,
        last_price=p.last_price,
        opened_at=p.opened_at,
        closed_at=p.closed_at,
    )


def _tout(t: PaperTrade, sym: dict[int, str]) -> TradeOut:
    return TradeOut(
        id=t.id,
        activation_id=t.activation_id,
        strategy_version_id=t.strategy_version_id,
        instrument_id=t.instrument_id,
        symbol=sym.get(t.instrument_id),
        side=t.side,
        quantity=t.quantity,
        entry_at=t.entry_at,
        entry_price=t.entry_price,
        exit_at=t.exit_at,
        exit_price=t.exit_price,
        gross_pnl=t.gross_pnl,
        costs=t.costs,
        net_pnl=t.net_pnl,
        entry_reason=t.entry_reason,
        exit_reason=t.exit_reason,
        bars_held=t.bars_held,
    )


async def _actout(db: DB, a: StrategyActivation) -> ActivationOut:
    v = await db.get(StrategyVersion, a.version_id)
    assert v is not None
    from core.db.models import Strategy

    s = await db.get(Strategy, v.strategy_id)
    assert s is not None
    sym = await _symbols(db, {a.instrument_id})
    return ActivationOut(
        id=a.id,
        version_id=a.version_id,
        strategy_id=s.id,
        strategy_name=s.name,
        version_no=v.version_no,
        trading_mode=a.trading_mode,
        paper_account_id=a.paper_account_id,
        instrument_id=a.instrument_id,
        symbol=sym.get(a.instrument_id),
        status=a.status,
        activated_at=a.activated_at,
        stopped_at=a.stopped_at,
        stop_reason=a.stop_reason,
    )


# ---------------------------------------------------------------- accounts
@router.get("/accounts", response_model=list[AccountOut])
async def list_accounts(db: DB, user: User) -> list[AccountOut]:
    rows = await db.execute(
        select(PaperAccount).where(PaperAccount.user_id == user.user_id).order_by(PaperAccount.id)
    )
    return [await _aout(db, a) for a in rows.scalars().all()]


@router.post("/accounts", response_model=AccountOut, status_code=status.HTTP_201_CREATED)
async def create_account(body: AccountIn, db: DB, state: State, user: User) -> AccountOut:
    cap = body.initial_capital or Decimal(state.settings.paper_default_capital)
    a = PaperAccount(
        user_id=user.user_id,
        name=body.name,
        currency="INR",
        initial_capital=cap,
        cash=cap,
        equity_hwm=cap,
        is_active=True,
    )
    db.add(a)
    await db.flush()
    await audit(
        db,
        user_id=user.user_id,
        action="paper.account.create",
        entity_type="paper_account",
        entity_id=a.id,
        after={"initial_capital": str(cap)},
    )
    await db.commit()
    return await _aout(db, a)


@router.get("/accounts/{account_id}", response_model=AccountOut)
async def get_account(account_id: int, db: DB, user: User) -> AccountOut:
    return await _aout(db, await _account(db, user, account_id))


@router.post("/accounts/{account_id}/reset", response_model=AccountOut)
async def reset_account(account_id: int, body: AccountIn, db: DB, user: User) -> AccountOut:
    """Start over: closes open positions as abandoned, resets cash to the new capital.
    History (orders, trades) is kept; `reset_at` marks the boundary."""
    a = await _account(db, user, account_id)
    active = (
        await db.execute(
            select(func.count(StrategyActivation.id)).where(
                StrategyActivation.paper_account_id == a.id,
                StrategyActivation.status == ActivationStatus.ACTIVE,
            )
        )
    ).scalar_one()
    if active:
        raise HTTPException(status.HTTP_409_CONFLICT, "stop active strategies before resetting")
    now = utcnow()
    for p in (
        await db.execute(
            select(PaperPosition).where(
                PaperPosition.paper_account_id == a.id, PaperPosition.closed_at.is_(None)
            )
        )
    ).scalars():
        p.closed_at = now
    cap = body.initial_capital or a.initial_capital
    before = {"cash": str(a.cash), "initial_capital": str(a.initial_capital)}
    a.initial_capital = cap
    a.cash = cap
    a.equity_hwm = cap
    a.reset_at = now
    if body.name:
        a.name = body.name
    await audit(
        db,
        user_id=user.user_id,
        action="paper.account.reset",
        entity_type="paper_account",
        entity_id=a.id,
        before=before,
        after={"initial_capital": str(cap)},
    )
    await db.commit()
    return await _aout(db, a)


# ---------------------------------------------------------------- orders / positions / trades
@router.get("/accounts/{account_id}/orders", response_model=list[OrderOut])
async def list_orders(
    account_id: int,
    db: DB,
    user: User,
    open_only: bool = False,
    limit: int = Query(default=200, ge=1, le=2000),
) -> list[OrderOut]:
    await _account(db, user, account_id)
    q = (
        select(PaperOrder)
        .where(PaperOrder.paper_account_id == account_id)
        .order_by(PaperOrder.submitted_at.desc())
        .limit(limit)
    )
    if open_only:
        q = q.where(
            PaperOrder.status.in_(
                [OrderStatus.SUBMITTED, OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED]
            )
        )
    orders = (await db.execute(q)).scalars().all()
    sym = await _symbols(db, {o.instrument_id for o in orders})
    return [_oout(o, sym) for o in orders]


@router.get("/orders/{order_id}/events", response_model=list[OrderEventOut])
async def order_events(order_id: int, db: DB, user: User) -> list[OrderEventOut]:
    o = await db.get(PaperOrder, order_id)
    if o is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "order not found")
    await _account(db, user, o.paper_account_id)
    rows = await db.execute(
        select(PaperOrderEvent)
        .where(PaperOrderEvent.order_id == order_id)
        .order_by(PaperOrderEvent.ts)
    )
    return [
        OrderEventOut(
            id=e.id,
            from_status=e.from_status,
            to_status=e.to_status,
            fill_qty=e.fill_qty,
            fill_px=e.fill_px,
            reason=e.reason,
            source=e.source,
            ts=e.ts,
        )
        for e in rows.scalars().all()
    ]


@router.get("/accounts/{account_id}/positions", response_model=list[PositionOut])
async def list_positions(
    account_id: int, db: DB, user: User, include_closed: bool = False
) -> list[PositionOut]:
    await _account(db, user, account_id)
    q = (
        select(PaperPosition)
        .where(PaperPosition.paper_account_id == account_id)
        .order_by(PaperPosition.opened_at.desc())
    )
    if not include_closed:
        q = q.where(PaperPosition.closed_at.is_(None))
    pos = (await db.execute(q)).scalars().all()
    sym = await _symbols(db, {p.instrument_id for p in pos})
    return [_pout(p, sym) for p in pos]


@router.get("/accounts/{account_id}/trades", response_model=list[TradeOut])
async def list_trades(
    account_id: int, db: DB, user: User, limit: int = Query(default=200, ge=1, le=5000)
) -> list[TradeOut]:
    await _account(db, user, account_id)
    rows = await db.execute(
        select(PaperTrade)
        .where(PaperTrade.paper_account_id == account_id)
        .order_by(PaperTrade.exit_at.desc())
        .limit(limit)
    )
    trades = rows.scalars().all()
    sym = await _symbols(db, {t.instrument_id for t in trades})
    return [_tout(t, sym) for t in trades]


# ---------------------------------------------------------------- activations
@router.get("/accounts/{account_id}/activations", response_model=list[ActivationOut])
async def list_activations(
    account_id: int, db: DB, user: User, all_statuses: bool = False
) -> list[ActivationOut]:
    await _account(db, user, account_id)
    q = select(StrategyActivation).where(StrategyActivation.paper_account_id == account_id)
    if not all_statuses:
        q = q.where(StrategyActivation.status != ActivationStatus.STOPPED)
    rows = (await db.execute(q.order_by(StrategyActivation.activated_at.desc()))).scalars().all()
    return [await _actout(db, a) for a in rows]


@router.post(
    "/accounts/{account_id}/activations",
    response_model=ActivationOut,
    status_code=status.HTTP_201_CREATED,
)
async def activate_strategy(
    account_id: int, body: ActivationIn, db: DB, user: User
) -> ActivationOut:
    """Run a strategy version on this paper account. The trader process picks it up on its
    next refresh. Paper never needs approval beyond a valid DSL (live does, ADR-007)."""
    acct = await _account(db, user, account_id)
    if not acct.is_active:
        raise HTTPException(status.HTTP_409_CONFLICT, "account inactive")
    v = await db.get(StrategyVersion, body.version_id)
    if v is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "version not found")
    from api.routers.strategies import PAPER_ELIGIBLE, _owned, _validate

    await _owned(db, user, v.strategy_id)
    if v.status not in PAPER_ELIGIBLE:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"version status {v.status.value} cannot paper trade"
        )
    val = _validate(v.dsl)
    if not val.valid:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, {"errors": val.errors})
    if await db.get(InstrumentRow, body.instrument_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "instrument not found")
    dup = (
        await db.execute(
            select(StrategyActivation).where(
                StrategyActivation.version_id == v.id,
                StrategyActivation.paper_account_id == acct.id,
                StrategyActivation.instrument_id == body.instrument_id,
                StrategyActivation.status != ActivationStatus.STOPPED,
            )
        )
    ).scalar_one_or_none()
    if dup is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "already active on this account/instrument")
    a = StrategyActivation(
        version_id=v.id,
        trading_mode=TradingMode.PAPER,
        paper_account_id=acct.id,
        live_account_id=None,
        instrument_id=body.instrument_id,
        params_override=body.params_override,
        status=ActivationStatus.ACTIVE,
        activated_by=user.user_id,
    )
    db.add(a)
    if v.status != StrategyVersionStatus.PAPER and v.status in (
        StrategyVersionStatus.BACKTESTED,
        StrategyVersionStatus.VALIDATED,
    ):
        v.status = StrategyVersionStatus.PAPER
    await db.flush()
    await audit(
        db,
        user_id=user.user_id,
        action="paper.activation.start",
        entity_type="strategy_activation",
        entity_id=a.id,
        after={"version_id": v.id, "instrument_id": body.instrument_id},
    )
    await db.commit()
    return await _actout(db, a)


class StopIn(BaseModel):
    reason: str = "stopped by user"
    flatten: bool = Field(default=True, description="Request the trader to square off its position")


@router.post("/activations/{activation_id}/stop", response_model=ActivationOut)
async def stop_activation(activation_id: int, body: StopIn, db: DB, user: User) -> ActivationOut:
    a = await db.get(StrategyActivation, activation_id)
    if a is None or a.paper_account_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "activation not found")
    await _account(db, user, a.paper_account_id)
    if await stop_paper_activation(
        db, a, reason=body.reason, flatten=body.flatten, user_id=user.user_id
    ):
        await db.commit()
    return await _actout(db, a)


@router.post("/activations/{activation_id}/pause", response_model=ActivationOut)
async def pause_activation(activation_id: int, db: DB, user: User) -> ActivationOut:
    a = await db.get(StrategyActivation, activation_id)
    if a is None or a.paper_account_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "activation not found")
    await _account(db, user, a.paper_account_id)
    a.status = (
        ActivationStatus.PAUSED if a.status == ActivationStatus.ACTIVE else ActivationStatus.ACTIVE
    )
    await audit(
        db,
        user_id=user.user_id,
        action="paper.activation.toggle",
        entity_type="strategy_activation",
        entity_id=a.id,
        after={"status": a.status.value},
    )
    await db.commit()
    return await _actout(db, a)
