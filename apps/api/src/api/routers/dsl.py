"""Strategy DSL introspection for the visual builder: the JSON Schema and a catalogue of
indicators, condition kinds and enums derived from the Pydantic models (never hand-copied)."""

from __future__ import annotations

from typing import Any, Literal, get_args, get_type_hints

from fastapi import APIRouter
from pydantic import BaseModel

from api.deps import User

router = APIRouter(prefix="/strategies/dsl", tags=["strategies"])

# Hints the indicator classes do not carry themselves (bounds for the form controls).
PARAM_HINTS: dict[str, dict[str, Any]] = {
    "period": {"type": "int", "min": 2, "max": 500, "default": 14},
    "fast": {"type": "int", "min": 2, "max": 200},
    "slow": {"type": "int", "min": 3, "max": 400},
    "signal": {"type": "int", "min": 2, "max": 100},
    "multiplier": {"type": "float", "min": 0.5, "max": 10},
    "std": {"type": "float", "min": 0.5, "max": 5},
    "minutes": {"type": "int", "min": 5, "max": 120},
    "lookback_bars": {"type": "int", "min": 1, "max": 100},
    "left": {"type": "int", "min": 1, "max": 50},
    "right": {"type": "int", "min": 1, "max": 50},
    "anchor": {"type": "enum", "options": ["session", "week", "month"]},
}
LABELS: dict[str, str] = {
    "VOLUME_SMA": "Volume SMA",
    "PREV_DAY": "Previous day",
    "OPENING_RANGE": "Opening range",
    "OI_CHANGE": "OI change",
    "DAILY_TREND": "Daily trend",
    "SUPERTREND": "Supertrend",
    "BOLLINGER": "Bollinger bands",
    "SWING": "Swing points",
}
DESCRIPTIONS: dict[str, str] = {
    "EMA": "Exponential moving average of a price field",
    "SMA": "Simple moving average of a price field",
    "RSI": "Relative strength index (Wilder)",
    "ATR": "Average true range (Wilder); used for stops, targets and sizing",
    "VWAP": "Session-anchored VWAP with standard-deviation bands",
    "SUPERTREND": "Supertrend value and direction label (up/down)",
    "BOLLINGER": "Bollinger bands: upper, middle, lower and width",
    "ADX": "Average directional index with +DI and -DI",
    "MACD": "MACD line, signal line and histogram",
    "VOLUME_SMA": "Simple moving average of volume",
    "PREV_DAY": "Previous session high, low and close",
    "OPENING_RANGE": "High and low of the first N minutes of the session",
    "OI_CHANGE": "Open-interest change over N bars (absolute and percent)",
    "SWING": "Most recent confirmed swing high and swing low",
    "DAILY_TREND": "Daily trend label (up/down/flat) from two daily EMAs",
}


class ParamSpec(BaseModel):
    name: str
    type: str
    default: Any = None
    min: float | None = None
    max: float | None = None
    options: list[str] | None = None


class IndicatorSpec(BaseModel):
    type: str
    label: str
    description: str
    params: list[ParamSpec]
    outputs: list[str]
    uses_price_field: bool


class Catalogue(BaseModel):
    dsl_schema_version: str
    indicators: list[IndicatorSpec]
    condition_kinds: list[str]
    operand_kinds: list[str]
    price_fields: list[str]
    compare_ops: list[str]
    cross_directions: list[str]
    slope_directions: list[str]
    arith_ops: list[str]
    level_units: list[str]
    structure_levels: list[str]
    trailing_modes: list[str]
    sizing_methods: list[str]
    products: list[str]
    directions: list[str]
    timeframes: list[str]
    universe_kinds: list[str]
    contract_expiries: list[str]
    contract_strikes: list[str]
    option_types: list[str]
    regime_sources: list[str]
    time_filter_modes: list[str]
    entry_order_types: list[str]
    stop_order_types: list[str]
    origins: list[str]
    languages: list[str]


def _lits(model: type[BaseModel], field: str) -> list[str]:
    """Literal values of a model field, unwrapping `X | None` and `Literal[...]`."""
    hint = get_type_hints(model)[field]
    if getattr(hint, "__origin__", None) is Literal:
        return [str(v) for v in get_args(hint)]
    out: list[str] = []
    for arg in get_args(hint):
        if getattr(arg, "__origin__", None) is Literal:
            out.extend(str(v) for v in get_args(arg))
    return out


def _alias_lits(alias: Any) -> list[str]:
    return [str(v) for v in get_args(alias)]


def build_catalogue() -> Catalogue:
    from strategy.dsl import schema as s
    from strategy.indicators import REGISTRY

    indicators: list[IndicatorSpec] = []
    for name, ind in REGISTRY.items():
        defaults: dict[str, Any] = dict(getattr(ind, "defaults", {}) or {})
        if not defaults and name in ("EMA", "SMA", "VOLUME_SMA"):
            defaults = {"period": 20}
        params: list[ParamSpec] = []
        for pname, dval in defaults.items():
            hint = PARAM_HINTS.get(pname, {})
            ptype = hint.get("type") or (
                "int" if isinstance(dval, int) else "float" if isinstance(dval, float) else "string"
            )
            params.append(
                ParamSpec(
                    name=pname,
                    type=ptype,
                    default=dval,
                    min=hint.get("min"),
                    max=hint.get("max"),
                    options=hint.get("options"),
                )
            )
        indicators.append(
            IndicatorSpec(
                type=name,
                label=LABELS.get(name, name),
                description=DESCRIPTIONS.get(name, ""),
                params=params,
                outputs=list(ind.outputs),
                uses_price_field=name in ("EMA", "SMA", "RSI", "BOLLINGER", "MACD"),
            )
        )
    return Catalogue(
        dsl_schema_version="1.0",
        indicators=indicators,
        condition_kinds=["compare", "cross", "between", "slope", "label", "group", "not"],
        operand_kinds=["indicator", "price", "const", "arith"],
        price_fields=_alias_lits(s.PriceField),
        compare_ops=_lits(s.Compare, "op"),
        cross_directions=_lits(s.Cross, "direction"),
        slope_directions=_lits(s.Slope, "direction"),
        arith_ops=_lits(s.ArithRef, "op"),
        level_units=_lits(s.LevelSpec, "unit"),
        structure_levels=_alias_lits(s.StructureLevel),
        trailing_modes=_lits(s.TrailingSpec, "mode"),
        sizing_methods=_lits(s.PositionSizing, "method"),
        products=_lits(s.SessionRules, "product"),
        directions=_lits(s.StrategyDocument, "direction"),
        timeframes=_alias_lits(s.Timeframe),
        universe_kinds=_lits(s.Universe, "kind"),
        contract_expiries=_lits(s.ContractSelector, "expiry"),
        contract_strikes=_lits(s.ContractSelector, "strike"),
        option_types=_lits(s.ContractSelector, "option_type"),
        regime_sources=_lits(s.RegimeFilter, "source"),
        time_filter_modes=_lits(s.TimeFilter, "mode"),
        entry_order_types=_lits(s.FillPreferences, "entry_order_type"),
        stop_order_types=_lits(s.FillPreferences, "stop_order_type"),
        origins=_lits(s.StrategyDocument, "origin"),
        languages=_lits(s.StrategyDocument, "language"),
    )


@router.get("/catalogue", response_model=Catalogue)
async def catalogue(_: User) -> Catalogue:
    return build_catalogue()


@router.get("/schema")
async def schema(_: User) -> dict[str, Any]:
    from strategy.dsl.json_schema import json_schema

    return json_schema()
