"""Risk limits and the inputs the engine needs. Limits are stored as JSONB in
`risk_limits.limits` and loaded into `RiskLimits`; defaults follow the discussion with the
owner: 1% per trade, 2% daily, 5% weekly, size halves beyond 10% drawdown."""

from __future__ import annotations

from datetime import time
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.models import OptionType, Position, ProductType, Segment


def _parse_hhmm(v: str | time) -> time:
    if isinstance(v, time):
        return v
    h, m = v.split(":")
    return time(int(h), int(m))


class RiskLimits(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_risk_per_trade_pct: float = Field(default=1.0, gt=0, le=100)
    max_daily_loss_pct: float = Field(default=2.0, gt=0, le=100)
    max_weekly_loss_pct: float = Field(default=5.0, gt=0, le=100)
    max_drawdown_pct: float = Field(default=10.0, gt=0, le=100)
    max_open_positions: int = Field(default=3, ge=1)
    max_lots_per_order: int = Field(default=10, ge=1)
    max_exposure_pct: float = Field(default=200.0, gt=0)
    max_correlated_exposure_pct: float = Field(default=100.0, gt=0)
    allow_short: bool = True
    allowed_products: frozenset[ProductType] = frozenset(
        {ProductType.INTRADAY, ProductType.DELIVERY, ProductType.CARRY}
    )
    trade_start: time = time(9, 20)
    no_new_entries_after: time = time(14, 45)
    square_off: time = time(15, 15)
    event_block: bool = True
    freeze_quantity_check: bool = True
    # Owner rule `pcr_guard` (docs/trading-rules.md): PCR = put OI / call OI, near expiry.
    pcr_no_put_buy_at: float = Field(default=2.0, gt=1)
    pcr_no_call_buy_at: float = Field(default=0.5, gt=0, lt=1)
    pcr_max_age_minutes: int = Field(default=15, ge=1)

    _hhmm = field_validator("trade_start", "no_new_entries_after", "square_off", mode="before")(
        _parse_hhmm
    )


class InstrumentMeta(BaseModel):
    model_config = ConfigDict(frozen=True)

    instrument_id: int
    symbol: str
    segment: Segment
    lot_size: int = Field(default=1, ge=1)
    tick_size: Decimal = Decimal("0.05")
    freeze_quantity: int | None = Field(default=None, description="Exchange freeze qty per order")
    underlying_symbol: str | None = None
    option_type: OptionType | None = None

    @property
    def correlation_key(self) -> str:
        """Instruments sharing an underlying are treated as one exposure bucket."""
        return self.underlying_symbol or self.symbol


class AccountState(BaseModel):
    model_config = ConfigDict(frozen=True)

    account_id: int
    equity: Decimal
    cash: Decimal
    realized_today: Decimal = Decimal("0")
    realized_week: Decimal = Decimal("0")
    peak_equity: Decimal | None = None
    open_positions: tuple[Position, ...] = ()
    exposure: Decimal = Field(default=Decimal("0"), description="Gross open notional")
    exposure_by_key: dict[str, Decimal] = Field(default_factory=dict)

    @property
    def open_count(self) -> int:
        return sum(1 for p in self.open_positions if not p.is_flat)

    def position_for(self, instrument_id: int) -> Position | None:
        for p in self.open_positions:
            if p.instrument_id == instrument_id and not p.is_flat:
                return p
        return None
