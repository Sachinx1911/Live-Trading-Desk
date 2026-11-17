"""Canonical market data records. Every record carries provenance (provider_id,
provider_ts, received_at). Timestamps are aware UTC (ADR-006)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from core.models.enums import Freshness, OptionType, Timeframe
from core.time import ensure_utc


class _Provenance(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider_id: str = Field(description="Provider code: upstox | dhan | fake | import")
    provider_ts: datetime | None = Field(default=None, description="Timestamp as sent by provider")
    received_at: datetime = Field(description="When we received/created this record (UTC)")
    is_demo: bool = False

    @field_validator("provider_ts", "received_at", mode="before")
    @classmethod
    def _utc(cls, v: datetime | None) -> datetime | None:
        return ensure_utc(v) if v is not None else None


class DepthLevel(BaseModel):
    model_config = ConfigDict(frozen=True)

    price: Decimal
    quantity: int
    orders: int | None = None


class Tick(_Provenance):
    instrument_id: int
    ts: datetime = Field(description="Exchange/event time (UTC)")
    ltp: Decimal
    ltq: int | None = None
    volume: int | None = Field(default=None, description="Cumulative session volume")
    oi: int | None = None
    bids: tuple[DepthLevel, ...] = ()
    asks: tuple[DepthLevel, ...] = ()

    _utc_ts = field_validator("ts", mode="before")(lambda v: ensure_utc(v))

    @property
    def best_bid(self) -> Decimal | None:
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> Decimal | None:
        return self.asks[0].price if self.asks else None


class Quote(_Provenance):
    """Latest snapshot for an instrument, as cached in Redis and shown in the UI."""

    instrument_id: int
    ts: datetime
    ltp: Decimal
    bid: Decimal | None = None
    ask: Decimal | None = None
    bid_qty: int | None = None
    ask_qty: int | None = None
    volume: int | None = None
    oi: int | None = None
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    prev_close: Decimal | None = None
    freshness: Freshness = Freshness.DISCONNECTED

    _utc_ts = field_validator("ts", mode="before")(lambda v: ensure_utc(v))

    @property
    def change(self) -> Decimal | None:
        return None if self.prev_close is None else self.ltp - self.prev_close

    @property
    def change_pct(self) -> Decimal | None:
        if self.prev_close in (None, 0):
            return None
        assert self.prev_close is not None
        return (self.ltp - self.prev_close) / self.prev_close * 100


class Candle(_Provenance):
    """OHLCV bar. `ts` is the bar OPEN time in UTC (ADR-006)."""

    instrument_id: int
    timeframe: Timeframe
    ts: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int = 0
    oi: int | None = None
    trade_count: int | None = None
    derived_from: Timeframe | None = Field(
        default=None, description="Set when resampled from a finer timeframe"
    )

    _utc_ts = field_validator("ts", mode="before")(lambda v: ensure_utc(v))

    @model_validator(mode="after")
    def _ohlc_consistent(self) -> Candle:
        if not (self.low <= self.open <= self.high and self.low <= self.close <= self.high):
            raise ValueError("OHLC inconsistent: open/close must lie within [low, high]")
        if self.volume < 0:
            raise ValueError("volume must be >= 0")
        return self


class OptionChainRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    instrument_id: int
    strike: Decimal
    option_type: OptionType
    ltp: Decimal | None = None
    bid: Decimal | None = None
    ask: Decimal | None = None
    volume: int | None = None
    oi: int | None = None
    oi_change: int | None = None
    iv: Decimal | None = None
    delta: Decimal | None = None
    theta: Decimal | None = None
    gamma: Decimal | None = None
    vega: Decimal | None = None


class OptionChainSnapshot(_Provenance):
    underlying_instrument_id: int
    expiry: datetime
    ts: datetime
    underlying_price: Decimal | None = None
    rows: tuple[OptionChainRow, ...] = ()

    _utc_ts = field_validator("ts", "expiry", mode="before")(lambda v: ensure_utc(v))
