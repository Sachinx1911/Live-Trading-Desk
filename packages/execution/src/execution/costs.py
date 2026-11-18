"""Indian transaction cost model (ADR-011). Rates are date-versioned in `cost_schedules`;
`StaticCostSchedule` is the built-in fallback with the published rates as of 2025-10.

All percentages are fractions of the traded notional (price x quantity). Options charges
apply to the premium notional. Results are rounded to paise."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol

from core.db.models._enums import ChargeSide, ChargeType, CostProduct, RateType
from core.models import OrderSide, ProductType, Segment

PAISA = Decimal("0.01")
GST_RATE = Decimal("0.18")  # 18% on brokerage + exchange txn + SEBI fee (CBIC notification)


@dataclass(frozen=True)
class Rate:
    charge: ChargeType
    side: ChargeSide
    rate_type: RateType
    rate: Decimal
    cap: Decimal | None = None
    effective_from: date = date(2025, 10, 1)
    effective_to: date | None = None

    def applies(self, side: OrderSide, on: date) -> bool:
        if on < self.effective_from or (self.effective_to and on > self.effective_to):
            return False
        return self.side == ChargeSide.BOTH or self.side.value == side.value


@dataclass(frozen=True)
class CostBreakdown:
    brokerage: Decimal = Decimal(0)
    stt: Decimal = Decimal(0)
    exchange: Decimal = Decimal(0)
    sebi: Decimal = Decimal(0)
    stamp: Decimal = Decimal(0)
    gst: Decimal = Decimal(0)

    @property
    def total(self) -> Decimal:
        return self.brokerage + self.stt + self.exchange + self.sebi + self.stamp + self.gst


class CostSchedule(Protocol):
    def rates(self, product: CostProduct) -> Iterable[Rate]: ...


def _paisa(v: Decimal) -> Decimal:
    return v.quantize(PAISA, rounding=ROUND_HALF_UP)


def _pct(v: str) -> Decimal:
    """Percent string -> fraction, e.g. "0.025" -> Decimal("0.00025")."""
    return Decimal(v) / Decimal(100)


@dataclass
class StaticCostSchedule:
    """Published NSE / SEBI / stamp-duty rates, effective 2025-10-01 unless noted.

    - Brokerage: flat Rs 20 per executed order (Upstox/discount-broker convention), both sides.
    - STT: equity delivery 0.1% both sides; equity intraday 0.025% sell; futures 0.02% sell;
      options 0.1% of premium on sell (raised from 0.0625% on 2024-10-01).
    - NSE transaction charges: equity 0.00297%; futures 0.00173%; options 0.03503% of premium
      (both sides).
    - SEBI turnover fee: Rs 10 per crore = 0.0001% both sides.
    - Stamp duty (buy side only): delivery 0.015%; intraday 0.003%; futures 0.002%;
      options 0.003%.
    - GST 18% on brokerage + exchange charges + SEBI fee.
    """

    brokerage_flat: Decimal = Decimal("20")
    _rates: dict[CostProduct, list[Rate]] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        b = Rate(
            ChargeType.BROKERAGE, ChargeSide.BOTH, RateType.FLAT_PER_ORDER, self.brokerage_flat
        )
        sebi = Rate(ChargeType.SEBI, ChargeSide.BOTH, RateType.PERCENT, _pct("0.0001"))
        self._rates = {
            CostProduct.DELIVERY: [
                b,
                Rate(ChargeType.STT, ChargeSide.BOTH, RateType.PERCENT, _pct("0.1")),
                Rate(ChargeType.EXCHANGE_TXN, ChargeSide.BOTH, RateType.PERCENT, _pct("0.00297")),
                sebi,
                Rate(ChargeType.STAMP_DUTY, ChargeSide.BUY, RateType.PERCENT, _pct("0.015")),
            ],
            CostProduct.INTRADAY: [
                b,
                Rate(ChargeType.STT, ChargeSide.SELL, RateType.PERCENT, _pct("0.025")),
                Rate(ChargeType.EXCHANGE_TXN, ChargeSide.BOTH, RateType.PERCENT, _pct("0.00297")),
                sebi,
                Rate(ChargeType.STAMP_DUTY, ChargeSide.BUY, RateType.PERCENT, _pct("0.003")),
            ],
            CostProduct.FUTURES: [
                b,
                Rate(ChargeType.STT, ChargeSide.SELL, RateType.PERCENT, _pct("0.02")),
                Rate(ChargeType.EXCHANGE_TXN, ChargeSide.BOTH, RateType.PERCENT, _pct("0.00173")),
                sebi,
                Rate(ChargeType.STAMP_DUTY, ChargeSide.BUY, RateType.PERCENT, _pct("0.002")),
            ],
            CostProduct.OPTIONS: [
                b,
                Rate(ChargeType.STT, ChargeSide.SELL, RateType.PERCENT, _pct("0.1")),
                Rate(ChargeType.EXCHANGE_TXN, ChargeSide.BOTH, RateType.PERCENT, _pct("0.03503")),
                sebi,
                Rate(ChargeType.STAMP_DUTY, ChargeSide.BUY, RateType.PERCENT, _pct("0.003")),
            ],
        }

    def rates(self, product: CostProduct) -> Iterable[Rate]:
        return self._rates[product]


class CostRow(Protocol):
    """Shape of a `cost_schedules` row (ORM object or any attribute bag)."""

    product: str
    charge_type: str
    side: str
    rate_type: str
    rate: object
    cap: object | None
    effective_from: date
    effective_to: date | None


class RowSchedule:
    """Schedule built from `cost_schedules` ORM rows (any object with the row's attributes).
    Rows whose `rate_type` is PERCENT must store the rate as a fraction (0.00025 for 0.025%)."""

    def __init__(self, rows: Iterable[CostRow]) -> None:
        self._rates: dict[CostProduct, list[Rate]] = {}
        for r in rows:
            product = CostProduct(r.product)
            self._rates.setdefault(product, []).append(
                Rate(
                    charge=ChargeType(r.charge_type),
                    side=ChargeSide(r.side),
                    rate_type=RateType(r.rate_type),
                    rate=Decimal(str(r.rate)),
                    cap=(Decimal(str(r.cap)) if r.cap is not None else None),
                    effective_from=r.effective_from,
                    effective_to=r.effective_to,
                )
            )

    def rates(self, product: CostProduct) -> Iterable[Rate]:
        return self._rates.get(product, [])


def cost_product(segment: Segment, product: ProductType) -> CostProduct:
    if segment == Segment.OPTIONS:
        return CostProduct.OPTIONS
    if segment == Segment.FUTURES:
        return CostProduct.FUTURES
    return CostProduct.INTRADAY if product == ProductType.INTRADAY else CostProduct.DELIVERY


class CostModel:
    def __init__(self, schedule: CostSchedule | None = None) -> None:
        self.schedule: CostSchedule = schedule or StaticCostSchedule()

    def compute(
        self,
        *,
        segment: Segment,
        product: ProductType,
        side: OrderSide,
        quantity: int,
        price: Decimal,
        lots: int = 1,
        on: date | None = None,
    ) -> CostBreakdown:
        """Charges for ONE executed order (fill) of `quantity` at `price`."""
        on = on or date.today()  # noqa: DTZ011 - calendar date of the trade, caller passes it
        notional = Decimal(quantity) * price
        parts: dict[ChargeType, Decimal] = {}
        for rate in self.schedule.rates(cost_product(segment, product)):
            if not rate.applies(side, on):
                continue
            if rate.rate_type == RateType.PERCENT:
                amt = notional * rate.rate
            elif rate.rate_type == RateType.FLAT_PER_ORDER:
                amt = rate.rate
            else:  # PER_LOT
                amt = rate.rate * lots
            if rate.cap is not None:
                amt = min(amt, rate.cap)
            parts[rate.charge] = parts.get(rate.charge, Decimal(0)) + amt
        brokerage = parts.get(ChargeType.BROKERAGE, Decimal(0))
        exchange = parts.get(ChargeType.EXCHANGE_TXN, Decimal(0)) + parts.get(
            ChargeType.CLEARING, Decimal(0)
        )
        sebi = parts.get(ChargeType.SEBI, Decimal(0))
        gst = (brokerage + exchange + sebi) * GST_RATE
        return CostBreakdown(
            brokerage=_paisa(brokerage),
            stt=_paisa(parts.get(ChargeType.STT, Decimal(0))),
            exchange=_paisa(exchange),
            sebi=_paisa(sebi),
            stamp=_paisa(parts.get(ChargeType.STAMP_DUTY, Decimal(0))),
            gst=_paisa(gst),
        )
