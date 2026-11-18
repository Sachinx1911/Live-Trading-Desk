"""Slippage models. Stochastic components draw from a seeded RNG so a run is reproducible."""

from __future__ import annotations

import random
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol

from core.models import OrderSide

BPS = Decimal(10_000)
TICK = Decimal("0.05")


def _to_tick(px: Decimal) -> Decimal:
    return (px / TICK).quantize(Decimal(1), rounding=ROUND_HALF_UP) * TICK


class SlippageModel(Protocol):
    def apply(self, price: Decimal, side: OrderSide, quantity: int, lot_size: int) -> Decimal: ...


class FixedBpsSlippage:
    """Price moves against the taker by a fixed number of basis points."""

    def __init__(self, bps: Decimal | float | int = 5) -> None:
        self.bps = Decimal(str(bps))

    def apply(self, price: Decimal, side: OrderSide, quantity: int, lot_size: int) -> Decimal:
        delta = price * self.bps / BPS
        return _to_tick(price + delta if side == OrderSide.BUY else price - delta)


class SpreadAwareSlippage:
    """Base bps plus a size impact per lot, jittered 0.5x-1.5x by the seeded RNG."""

    def __init__(
        self,
        base_bps: Decimal | float | int = 2,
        size_impact_per_lot: Decimal | float | int = 0.5,
        seed: int = 42,
    ) -> None:
        self.base_bps = Decimal(str(base_bps))
        self.size_impact = Decimal(str(size_impact_per_lot))
        self.rng = random.Random(seed)  # noqa: S311 - simulation, not security

    def apply(self, price: Decimal, side: OrderSide, quantity: int, lot_size: int) -> Decimal:
        lots = max(1, quantity // max(1, lot_size))
        jitter = Decimal(str(round(self.rng.uniform(0.5, 1.5), 4)))
        bps = self.base_bps + self.size_impact * lots * jitter
        delta = price * bps / BPS
        return _to_tick(price + delta if side == OrderSide.BUY else price - delta)
