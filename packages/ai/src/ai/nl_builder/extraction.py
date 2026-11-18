"""What the model is allowed to say: a structured extraction of the trader's text.

Deliberately *not* the DSL. The vocabulary is small (indicator, price, number; a dozen
comparisons; four level units; four sizing methods) so the model cannot invent structure,
and every condition, level and sizing carries `original_phrase`: the trader's own words it
came from, shown back in the UI so a wrong reading is caught before anything is saved.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from strategy.dsl.schema import IndicatorType, PriceField, Timeframe

Comparison = Literal[
    "crosses_above",
    "crosses_below",
    "greater_than",
    "greater_or_equal",
    "less_than",
    "less_or_equal",
    "equals",
    "between",
    "rising",
    "falling",
]
Language = Literal["mr", "hi", "en"]
Direction = Literal["long_only", "short_only", "both"]
QuestionField = Literal[
    "entry_conditions",
    "exit_conditions",
    "stop_loss",
    "target",
    "position_sizing",
    "session",
    "direction",
    "timeframe",
    "instrument",
    "other",
]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NLIndicator(_Model):
    type: IndicatorType
    period: int | None = Field(default=None, ge=1, description="Only when the text states one")
    params: dict[str, float | int | str] = Field(
        default_factory=dict,
        description="Other stated parameters, e.g. {'multiplier': 3} or {'std': 2}",
    )
    output: str | None = Field(
        default=None,
        description="For multi-output indicators: upper/middle/lower, macd/signal/hist, ...",
    )
    source: PriceField = "close"
    timeframe: Timeframe | None = Field(
        default=None, description="Only when the text names a different timeframe for it"
    )


class NLOperand(_Model):
    kind: Literal["indicator", "price", "number"]
    indicator: NLIndicator | None = None
    price: PriceField | None = None
    number: float | None = None

    @model_validator(mode="after")
    def _one_of(self) -> NLOperand:
        present = {
            "indicator": self.indicator is not None,
            "price": self.price is not None,
            "number": self.number is not None,
        }
        if not present[self.kind]:
            raise ValueError(f"operand kind={self.kind} needs its `{self.kind}` field")
        return self


class NLCondition(_Model):
    original_phrase: str = Field(min_length=1, description="The trader's words for this rule")
    left: NLOperand
    comparison: Comparison
    right: NLOperand | None = None
    low: NLOperand | None = Field(default=None, description="between: lower bound")
    high: NLOperand | None = Field(default=None, description="between: upper bound")
    bars: int | None = Field(default=None, ge=1, description="rising/falling: over how many bars")

    @model_validator(mode="after")
    def _shape(self) -> NLCondition:
        if self.comparison == "between":
            if self.low is None or self.high is None:
                raise ValueError("between needs low and high")
        elif self.comparison in ("rising", "falling"):
            pass
        elif self.right is None:
            raise ValueError(f"{self.comparison} needs a right operand")
        return self


class NLConditionSet(_Model):
    op: Literal["and", "or"] = "and"
    conditions: list[NLCondition] = Field(min_length=1, max_length=10)


class NLLevel(_Model):
    original_phrase: str = Field(min_length=1)
    unit: Literal["points", "percent", "atr", "rr"]
    value: float = Field(gt=0)
    atr_period: int | None = Field(default=None, ge=1, description="unit=atr: only if stated")


class NLSizing(_Model):
    original_phrase: str = Field(min_length=1)
    method: Literal["fixed_lots", "fixed_quantity", "fixed_capital", "risk_percent"]
    value: float = Field(gt=0)


class NLSession(_Model):
    product: Literal["INTRADAY", "DELIVERY", "CARRY_FORWARD"] | None = None
    trade_start: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    no_new_entries_after: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    square_off_at: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")


class ClarificationQuestion(_Model):
    id: str = Field(pattern=r"^q[0-9]{1,3}$")
    field: QuestionField
    question_local: str = Field(min_length=1, description="In the trader's language")
    question_en: str = Field(min_length=1)


class NLExtraction(_Model):
    """Model output. Everything optional is None unless the text states it."""

    strategy_name: str = Field(min_length=1, max_length=80)
    detected_language: Language
    direction: Direction | None = None
    timeframe: Timeframe | None = Field(default=None, description="Only if the text states one")
    entry_long: NLConditionSet | None = None
    entry_short: NLConditionSet | None = None
    exit_long: NLConditionSet | None = None
    exit_short: NLConditionSet | None = None
    stop_loss: NLLevel | None = None
    target: NLLevel | None = None
    position_sizing: NLSizing | None = None
    session: NLSession | None = None
    max_trades_per_day: int | None = Field(default=None, ge=1)
    unsupported: list[str] = Field(
        default_factory=list,
        description="Trader phrases naming indicators or rules outside the fixed library",
    )
    clarification_questions: list[ClarificationQuestion] = Field(default_factory=list)


# Extraction fields grouped by the clarification `field` they belong to. Used to decide
# which model changes an answer may legitimately cause.
FIELD_GROUPS: dict[str, tuple[str, ...]] = {
    "entry_conditions": ("entry_long", "entry_short"),
    "exit_conditions": ("exit_long", "exit_short"),
    "stop_loss": ("stop_loss",),
    "target": ("target",),
    "position_sizing": ("position_sizing",),
    "session": ("session", "max_trades_per_day"),
    "direction": ("direction",),
    "timeframe": ("timeframe",),
}
