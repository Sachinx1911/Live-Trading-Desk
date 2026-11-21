"""Strategy DSL v1 — Pydantic models (docs/architecture/05-strategy-dsl.md, ADR-003).

The document is declarative. Intent fields (entry, exit, stop, target, sizing) default to
None so a natural-language draft can be stored before the user answers clarifications.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

DSL_SCHEMA_VERSION = "1.1"
# 1.1 (Mark 1, Stage 2) adds the `option` operand; every 1.0 document is still valid 1.1.
SUPPORTED_DSL_VERSIONS = ("1.0", "1.1")

Timeframe = Literal["1m", "3m", "5m", "15m", "30m", "1h", "1d", "1w"]
PriceField = Literal["open", "high", "low", "close", "volume", "oi"]
IndicatorType = Literal[
    "EMA",
    "SMA",
    "RSI",
    "ATR",
    "VWAP",
    "SUPERTREND",
    "BOLLINGER",
    "ADX",
    "MACD",
    "VOLUME_SMA",
    "PREV_DAY",
    "OPENING_RANGE",
    "OI_CHANGE",
    "SWING",
    "DAILY_TREND",
]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------- universe
class ContractSelector(_Model):
    expiry: Literal["current_week", "next_week", "current_month", "next_month"]
    option_type: Literal["CE", "PE"] | None = None
    strike: Literal["ATM", "ITM1", "ITM2", "OTM1", "OTM2", "OTM3"] | None = None
    roll_days_before_expiry: int = Field(default=1, ge=0)


class Universe(_Model):
    kind: Literal["instrument", "underlying_future", "underlying_option", "watchlist", "scanner"]
    instrument_ids: list[str] = []
    underlying: str | None = None
    contract: ContractSelector | None = None
    watchlist_id: str | None = None
    scanner_id: str | None = None


# ----------------------------------------------------------------------------- session
class SessionRules(_Model):
    product: Literal["INTRADAY", "DELIVERY", "CARRY_FORWARD"]
    trade_start: str | None = None
    no_new_entries_after: str | None = None
    square_off_at: str | None = None
    skip_first_minutes: int = Field(default=0, ge=0)
    trade_on_expiry_day: bool = True
    allowed_weekdays: list[int] = [0, 1, 2, 3, 4]


class RegimeFilter(_Model):
    source: Literal["vix", "adx", "daily_trend", "regime_label"]
    min: float | None = None
    max: float | None = None
    indicator_id: str | None = None
    allowed: list[str] | None = None


class TimeFilter(_Model):
    start: str
    end: str
    mode: Literal["allow_entries", "block_entries"]


# -------------------------------------------------------------------------- indicators
class IndicatorSpec(_Model):
    type: IndicatorType
    params: dict[str, float | int | str] = {}
    source: PriceField = "close"
    timeframe: Timeframe | None = None


# ---------------------------------------------------------------------------- operands
class IndicatorRef(_Model):
    kind: Literal["indicator"]
    id: str
    field: str = "value"
    offset: int = Field(default=0, ge=0)


class PriceRef(_Model):
    kind: Literal["price"]
    field: PriceField
    offset: int = Field(default=0, ge=0)


class ConstRef(_Model):
    kind: Literal["const"]
    value: float


class ArithRef(_Model):
    kind: Literal["arith"]
    op: Literal["+", "-", "*", "/"]
    left: Operand
    right: Operand


OptionFeature = Literal["pcr", "iv_atm", "oi", "oi_change_from_open", "greek"]
OptionSide = Literal["CE", "PE"]
Greek = Literal["delta", "gamma", "theta", "vega", "iv"]
_PER_STRIKE: tuple[str, ...] = ("oi", "oi_change_from_open", "greek")


class OptionRef(_Model):
    """Option-chain fact of the traded instrument's underlying (DSL 1.1), read from the last
    stored chain snapshot at or before the bar's time (never later):

    - `pcr`: total put OI / total call OI of the nearest expiry.
    - `iv_atm`: implied volatility (%) of the ATM strike, mean of call and put.
    - `oi` / `oi_change_from_open`: OI of one strike and side, or its change since the day's
      opening snapshot (09:15 IST).
    - `greek`: one Greek (or IV) of one strike and side.

    Strikes are chosen relative to the ATM strike at that moment: `strike_offset` 0 is ATM,
    +1 the next strike above, -1 the next below. Missing data gives no value (condition false).
    """

    kind: Literal["option"]
    feature: OptionFeature
    side: OptionSide | None = None
    strike_offset: int = Field(default=0, ge=-10, le=10)
    greek: Greek | None = None

    @model_validator(mode="after")
    def _fields_match_feature(self) -> OptionRef:
        if self.feature in _PER_STRIKE and self.side is None:
            raise ValueError(f"option feature {self.feature} needs side CE or PE")
        if self.feature == "greek" and self.greek is None:
            raise ValueError("option feature greek needs greek")
        if self.feature != "greek" and self.greek is not None:
            raise ValueError("greek is only used with feature greek")
        if self.feature in ("pcr", "iv_atm") and (self.side is not None or self.strike_offset):
            raise ValueError(f"option feature {self.feature} takes no side or strike_offset")
        return self


Operand = Annotated[
    IndicatorRef | PriceRef | ConstRef | ArithRef | OptionRef, Field(discriminator="kind")
]


# -------------------------------------------------------------------------- conditions
class Compare(_Model):
    kind: Literal["compare"]
    left: Operand
    op: Literal["gt", "gte", "lt", "lte", "eq"]
    right: Operand


class Cross(_Model):
    kind: Literal["cross"]
    left: Operand
    direction: Literal["crosses_above", "crosses_below"]
    right: Operand


class Between(_Model):
    kind: Literal["between"]
    value: Operand
    low: Operand
    high: Operand


class Slope(_Model):
    kind: Literal["slope"]
    value: Operand
    direction: Literal["rising", "falling"]
    bars: int = Field(ge=1)
    strict: bool = False


class Label(_Model):
    kind: Literal["label"]
    value: IndicatorRef
    equals: str | float


class Group(_Model):
    kind: Literal["group"]
    op: Literal["and", "or"]
    conditions: list[Condition] = Field(min_length=1, max_length=10)


class Not(_Model):
    kind: Literal["not"]
    condition: Condition


Condition = Annotated[
    Compare | Cross | Between | Slope | Label | Group | Not, Field(discriminator="kind")
]


# ------------------------------------------------------------------------ entry / exit
class EntryRules(_Model):
    long: Condition | None = None
    short: Condition | None = None
    confirm_bars: int = Field(default=0, ge=0)
    cooldown_bars: int = Field(default=0, ge=0)
    one_entry_per_signal: bool = True


class ExitRules(_Model):
    long: Condition | None = None
    short: Condition | None = None
    time_exit_bars: int | None = Field(default=None, ge=1)
    exit_on_opposite_signal: bool = False


# ------------------------------------------------------------------ stop/target/trail
StructureLevel = Literal[
    "swing_low",
    "swing_high",
    "prev_day_low",
    "prev_day_high",
    "opening_range_low",
    "opening_range_high",
]


class LevelSpec(_Model):
    unit: Literal["points", "percent", "atr", "structure", "indicator"]
    value: float | None = None
    atr_indicator_id: str | None = None
    structure: StructureLevel | None = None
    structure_indicator_id: str | None = None
    indicator_ref: IndicatorRef | None = None
    buffer_points: float = 0


class StopSpec(LevelSpec):
    pass


class PartialTarget(_Model):
    at: LevelSpec
    close_pct: float = Field(gt=0, le=100)
    move_stop_to_breakeven: bool = False


class TargetSpec(LevelSpec):
    unit: Literal["points", "percent", "atr", "structure", "indicator"] | None = None  # type: ignore[assignment]
    rr_multiple: float | None = Field(default=None, gt=0)
    partial: list[PartialTarget] = []


class TrailingSpec(_Model):
    mode: Literal["atr", "percent", "points", "indicator", "swing"]
    value: float | None = None
    atr_indicator_id: str | None = None
    indicator_ref: IndicatorRef | None = None
    activate_after: LevelSpec | None = None


# ------------------------------------------------------------------------------ sizing
class PositionSizing(_Model):
    method: Literal["fixed_lots", "fixed_quantity", "fixed_capital", "risk_percent"]
    lots: int | None = Field(default=None, ge=1)
    quantity: int | None = Field(default=None, ge=1)
    capital: float | None = Field(default=None, gt=0)
    risk_percent: float | None = Field(default=None, gt=0, le=100)
    max_lots: int | None = Field(default=None, ge=1)
    max_capital_pct: float | None = Field(default=None, gt=0, le=100)


class FillPreferences(_Model):
    entry_order_type: Literal["MARKET", "LIMIT_AT_CLOSE", "LIMIT_OFFSET"] = "MARKET"
    limit_offset_points: float = 0
    limit_timeout_bars: int = Field(default=1, ge=1)
    stop_order_type: Literal["SL_MARKET", "SL_LIMIT"] = "SL_MARKET"


# ---------------------------------------------------------------------------- document
class StrategyDocument(_Model):
    dsl_schema_version: Literal["1.0", "1.1"]
    name: str = Field(max_length=80)
    description: str | None = None
    origin: Literal["user_nl", "user_visual", "ai_research", "import"]
    original_text: str | None = None
    language: Literal["mr", "hi", "en"] | None = None

    market: str
    universe: Universe
    timeframe: Timeframe
    context_timeframes: list[Timeframe] = []

    session: SessionRules
    regime_filters: list[RegimeFilter] = []
    time_filters: list[TimeFilter] = []

    indicators: dict[str, IndicatorSpec] = {}

    entry: EntryRules | None = None
    exit: ExitRules | None = None
    stop_loss: StopSpec | None = None
    target: TargetSpec | None = None
    trailing: TrailingSpec | None = None

    position_sizing: PositionSizing | None = None
    max_positions: int = Field(default=1, ge=1)
    max_trades_per_day: int | None = Field(default=None, ge=1)
    direction: Literal["long_only", "short_only", "both"] = "long_only"

    fill: FillPreferences = FillPreferences()
    metadata: dict[str, str] = {}

    @model_validator(mode="after")
    def _basic(self) -> StrategyDocument:
        if len(self.context_timeframes) > 2:
            raise ValueError("context_timeframes: at most 2 allowed")
        return self


# Pydantic needs the recursive unions resolved after all classes exist.
ArithRef.model_rebuild()
Group.model_rebuild()
Not.model_rebuild()
Compare.model_rebuild()
Cross.model_rebuild()
Between.model_rebuild()
Slope.model_rebuild()
EntryRules.model_rebuild()
ExitRules.model_rebuild()
StrategyDocument.model_rebuild()
