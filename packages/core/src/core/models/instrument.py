"""Canonical instrument identity. Provider symbols/tokens live in instrument_mappings."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from core.models.enums import AssetClass, OptionType, Segment


class InstrumentRef(BaseModel):
    """Minimal reference used inside market data and trading records."""

    model_config = ConfigDict(frozen=True)

    instrument_id: int
    exchange: str = Field(description="Exchange code, e.g. NSE")
    symbol: str = Field(description="Canonical symbol, e.g. NIFTY, RELIANCE, NIFTY24NOV24000CE")


class Instrument(BaseModel):
    model_config = ConfigDict(frozen=True)

    instrument_id: int
    exchange: str
    segment: Segment
    asset_class: AssetClass
    symbol: str
    name: str
    isin: str | None = None
    underlying_symbol: str | None = None
    expiry: date | None = None
    strike: Decimal | None = None
    option_type: OptionType | None = None
    lot_size: int = 1
    tick_size: Decimal = Decimal("0.05")
    currency: str = "INR"
    is_active: bool = True

    @property
    def is_derivative(self) -> bool:
        return self.segment in {Segment.FUTURES, Segment.OPTIONS}

    def ref(self) -> InstrumentRef:
        return InstrumentRef(
            instrument_id=self.instrument_id, exchange=self.exchange, symbol=self.symbol
        )
