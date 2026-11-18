"""Position sizing. Every rule is explicit and ordered; the result records the binding
constraint so the journal can explain why a trade was this size."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_DOWN, Decimal

from core.models import Signal
from risk.limits import AccountState, InstrumentMeta, RiskLimits


@dataclass(frozen=True)
class SizingResult:
    quantity: int
    lots: int
    risk_amount: Decimal
    risk_per_unit: Decimal | None
    notional: Decimal
    reason: str
    notes: tuple[str, ...] = field(default_factory=tuple)


def _pct(x: Decimal, pct: float) -> Decimal:
    return (x * Decimal(str(pct)) / Decimal(100)).quantize(Decimal("0.01"))


def drawdown_factor(account: AccountState, limits: RiskLimits) -> Decimal:
    """Rule D: beyond max_drawdown_pct from peak equity, size halves until a new peak."""
    if account.peak_equity is None or account.peak_equity <= 0:
        return Decimal(1)
    floor = account.peak_equity * (Decimal(1) - Decimal(str(limits.max_drawdown_pct)) / 100)
    return Decimal("0.5") if account.equity < floor else Decimal(1)


def size_order(
    signal: Signal,
    limits: RiskLimits,
    account: AccountState,
    instrument: InstrumentMeta,
    price: Decimal,
) -> SizingResult:
    """Size an ENTRY. Rules, in order:

    R1 risk budget   = equity x max_risk_per_trade_pct, halved in drawdown (rule D).
    R2 quantity      = floor(budget / |reference - stop|) when a stop exists; else the
                       strategy's suggested_quantity; else one lot.
    R3 suggested     = if the strategy suggested a quantity, it is a CAP, never a floor.
    R4 lot rounding  = floor to lot multiples; a size below one lot becomes 0 (rejected
                       upstream) unless the risk budget covers one lot's risk.
    R5 lots cap      = max_lots_per_order.
    R6 exposure cap  = notional after trade <= equity x max_exposure_pct.
    R7 freeze qty    = per-order quantity <= exchange freeze quantity (note; caller splits).
    """
    notes: list[str] = []
    lot = max(instrument.lot_size, 1)
    factor = drawdown_factor(account, limits)
    budget = _pct(account.equity, limits.max_risk_per_trade_pct) * factor
    if factor < 1:
        notes.append("drawdown: size halved")

    risk_per_unit: Decimal | None = None
    if signal.stop_price is not None:
        risk_per_unit = abs(signal.reference_price - signal.stop_price)
        if risk_per_unit <= 0:
            risk_per_unit = None

    reason = "risk_percent"
    if risk_per_unit is not None:
        qty = int((budget / risk_per_unit).to_integral_value(rounding=ROUND_DOWN))
    elif signal.suggested_quantity:
        qty = signal.suggested_quantity
        reason = "suggested_quantity"
    else:
        qty = lot
        reason = "one_lot_default"

    if signal.suggested_quantity and qty > signal.suggested_quantity:
        qty = signal.suggested_quantity
        reason = "suggested_quantity_cap"

    lots = qty // lot
    if lots == 0 and risk_per_unit is not None and risk_per_unit * lot <= budget:
        lots = 1
    qty = lots * lot

    if lots > limits.max_lots_per_order:
        lots = limits.max_lots_per_order
        qty = lots * lot
        reason = "max_lots_per_order"

    if price > 0:
        room = _pct(account.equity, limits.max_exposure_pct) - account.exposure
        max_by_exposure = int((room / price).to_integral_value(rounding=ROUND_DOWN)) // lot
        if max_by_exposure < lots:
            lots = max(max_by_exposure, 0)
            qty = lots * lot
            reason = "max_exposure"

    if (
        limits.freeze_quantity_check
        and instrument.freeze_quantity
        and qty > instrument.freeze_quantity
    ):
        notes.append(f"exceeds freeze quantity {instrument.freeze_quantity}; split into slices")

    risk_amount = (risk_per_unit or Decimal(0)) * qty
    return SizingResult(
        quantity=qty,
        lots=lots,
        risk_amount=risk_amount,
        risk_per_unit=risk_per_unit,
        notional=price * qty,
        reason=reason,
        notes=tuple(notes),
    )
