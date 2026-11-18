"""Shorthand for expected rules in the evaluation set.

Conditions   `EMA(9) crosses_above EMA(21)` · `RSI() > 55` · `close < VWAP()`
             `RSI(14) between 40 and 60` · `ADX(14) rising 3` · `BOLLINGER(20,std=2).upper`
             operand = NAME(args)[.output][@tf][[source]] | open|high|low|close|volume|oi | number
             args    = bare integer → period, key=value → param
             cmp     = crosses_above | crosses_below | > | >= | < | <= | ==
Levels       `1.5 atr` · `20 points` · `0.5 percent` · `2 rr` (atr may add `(10)` for the period)
Sizing       `1 lots` · `50 quantity` · `100000 capital` · `1 risk_percent`
"""

from __future__ import annotations

import re
from typing import Any, Literal, cast

from ai.nl_builder.extraction import (
    Comparison,
    Direction,
    Language,
    NLCondition,
    NLConditionSet,
    NLExtraction,
    NLIndicator,
    NLLevel,
    NLOperand,
    NLSession,
    NLSizing,
)
from strategy.dsl.schema import IndicatorType, PriceField, Timeframe

PRICE_FIELDS = ("open", "high", "low", "close", "volume", "oi")
CMP_TOKENS: dict[str, Comparison] = {
    "crosses_above": "crosses_above",
    "crosses_below": "crosses_below",
    ">": "greater_than",
    ">=": "greater_or_equal",
    "<": "less_than",
    "<=": "less_or_equal",
    "==": "equals",
}
_IND_RE = re.compile(
    r"^(?P<name>[A-Z_]+)\((?P<args>[^)]*)\)"
    r"(?:\.(?P<out>[a-z_0-9]+))?"
    r"(?:@(?P<tf>[0-9]+[mhdw]))?"
    r"(?:\[(?P<src>[a-z]+)\])?$"
)
_NUM_RE = re.compile(r"^-?\d+(\.\d+)?$")


class ShorthandError(ValueError):
    pass


def _num(s: str) -> float:
    if not _NUM_RE.match(s):
        raise ShorthandError(f"not a number: {s!r}")
    return float(s)


def parse_operand(tok: str) -> NLOperand:
    tok = tok.strip()
    if tok in PRICE_FIELDS:
        return NLOperand(kind="price", price=cast(PriceField, tok))
    if _NUM_RE.match(tok):
        return NLOperand(kind="number", number=float(tok))
    m = _IND_RE.match(tok)
    if not m:
        raise ShorthandError(f"cannot parse operand {tok!r}")
    period: int | None = None
    params: dict[str, float | int | str] = {}
    for raw in filter(None, (a.strip() for a in m.group("args").split(","))):
        if "=" in raw:
            k, v = (x.strip() for x in raw.split("=", 1))
            params[k] = int(v) if re.fullmatch(r"-?\d+", v) else float(v) if _NUM_RE.match(v) else v
        elif re.fullmatch(r"\d+", raw):
            period = int(raw)
        else:
            raise ShorthandError(f"bad indicator argument {raw!r} in {tok!r}")
    ind = NLIndicator(
        type=cast(IndicatorType, m.group("name")),
        period=period,
        params=params,
        output=m.group("out"),
        source=cast(PriceField, m.group("src") or "close"),
        timeframe=cast(Timeframe, m.group("tf")) if m.group("tf") else None,
    )
    return NLOperand(kind="indicator", indicator=ind)


def parse_condition(text: str) -> NLCondition:
    parts = text.split()
    if len(parts) >= 5 and parts[1] == "between" and parts[3] == "and":
        return NLCondition(
            original_phrase=text,
            left=parse_operand(parts[0]),
            comparison="between",
            low=parse_operand(parts[2]),
            high=parse_operand(" ".join(parts[4:])),
        )
    if len(parts) in (2, 3) and parts[1] in ("rising", "falling"):
        return NLCondition(
            original_phrase=text,
            left=parse_operand(parts[0]),
            comparison=cast(Comparison, parts[1]),
            bars=int(parts[2]) if len(parts) == 3 else None,
        )
    if len(parts) != 3 or parts[1] not in CMP_TOKENS:
        raise ShorthandError(f"cannot parse condition {text!r}")
    return NLCondition(
        original_phrase=text,
        left=parse_operand(parts[0]),
        comparison=CMP_TOKENS[parts[1]],
        right=parse_operand(parts[2]),
    )


def parse_set(rules: list[str] | None, op: str = "and") -> NLConditionSet | None:
    if not rules:
        return None
    return NLConditionSet(
        op=cast(Literal["and", "or"], op), conditions=[parse_condition(r) for r in rules]
    )


_LEVEL_RE = re.compile(r"^(?P<v>\d+(\.\d+)?)\s*(?P<u>points|percent|atr|rr)(?:\((?P<p>\d+)\))?$")


def parse_level(text: str | None) -> NLLevel | None:
    if text is None:
        return None
    m = _LEVEL_RE.match(text.strip())
    if not m:
        raise ShorthandError(f"cannot parse level {text!r}")
    return NLLevel(
        original_phrase=text,
        unit=cast(Literal["points", "percent", "atr", "rr"], m.group("u")),
        value=float(m.group("v")),
        atr_period=int(m.group("p")) if m.group("p") else None,
    )


_SIZING_RE = re.compile(r"^(?P<v>\d+(\.\d+)?)\s*(?P<m>lots|quantity|capital|risk_percent)$")
_SIZING_METHOD = {
    "lots": "fixed_lots",
    "quantity": "fixed_quantity",
    "capital": "fixed_capital",
    "risk_percent": "risk_percent",
}


def parse_sizing(text: str | None) -> NLSizing | None:
    if text is None:
        return None
    m = _SIZING_RE.match(text.strip())
    if not m:
        raise ShorthandError(f"cannot parse sizing {text!r}")
    return NLSizing(
        original_phrase=text,
        method=cast(
            Literal["fixed_lots", "fixed_quantity", "fixed_capital", "risk_percent"],
            _SIZING_METHOD[m.group("m")],
        ),
        value=float(m.group("v")),
    )


def extraction_from_expect(expect: dict[str, Any], *, name: str, lang: Language) -> NLExtraction:
    """Build the extraction a correct model answer would produce for a case."""
    session = expect.get("session")
    return NLExtraction(
        strategy_name=name,
        detected_language=lang,
        direction=cast(Direction | None, expect.get("direction")),
        entry_long=parse_set(expect.get("entry_long"), expect.get("entry_long_op", "and")),
        entry_short=parse_set(expect.get("entry_short"), expect.get("entry_short_op", "and")),
        exit_long=parse_set(expect.get("exit_long"), expect.get("exit_long_op", "and")),
        exit_short=parse_set(expect.get("exit_short"), expect.get("exit_short_op", "and")),
        stop_loss=parse_level(expect.get("stop_loss")),
        target=parse_level(expect.get("target")),
        position_sizing=parse_sizing(expect.get("sizing")),
        session=NLSession.model_validate(session) if session else None,
        max_trades_per_day=expect.get("max_trades_per_day"),
        unsupported=["(expected)"] if expect.get("unsupported") else [],
    )
