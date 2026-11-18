"""Deterministic extraction → Strategy DSL v1 compiler.

No model in the loop: the same extraction always yields the same DSL. Anything the trader
did not say stays `null`; the few structural defaults the DSL needs to be a document at
all (session product, index → current-month future) are applied *and listed* in
`defaults_applied`, so the UI can show them and the user can change them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ai.nl_builder.extraction import (
    NLCondition,
    NLConditionSet,
    NLExtraction,
    NLIndicator,
    NLLevel,
    NLOperand,
    NLSizing,
)
from strategy.dsl.schema import DSL_SCHEMA_VERSION
from strategy.indicators import OUTPUTS, REGISTRY

# Index underlyings cannot be traded directly; the draft targets the current-month future
# (the user can switch to options or another contract in the editor).
INDEX_UNDERLYINGS = frozenset({"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX", "BANKEX"})
DEFAULT_ATR_PERIOD = 14
# Applied (and listed in defaults_applied) when the text names the indicator without a period.
# EMA/SMA are deliberately absent: their period *is* the rule, so it must be stated.
DEFAULT_PERIODS: dict[str, int] = {"RSI": 14, "ATR": 14, "ADX": 14, "VOLUME_SMA": 20}
DEFAULT_SLOPE_BARS = 1

COMPARE_OPS = {
    "greater_than": "gt",
    "greater_or_equal": "gte",
    "less_than": "lt",
    "less_or_equal": "lte",
    "equals": "eq",
}


@dataclass
class CompileResult:
    dsl: dict[str, Any]
    errors: list[str] = field(default_factory=list)  # things the model said that cannot compile
    warnings: list[str] = field(default_factory=list)
    defaults_applied: list[str] = field(default_factory=list)


class _Compiler:
    def __init__(self) -> None:
        self.indicators: dict[str, dict[str, Any]] = {}
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.defaults: list[str] = []

    # --- indicators -------------------------------------------------------------------

    def indicator_id(self, spec: NLIndicator, where: str) -> str | None:
        reg = REGISTRY[spec.type]
        params: dict[str, float | int | str] = dict(spec.params)
        if spec.period is not None:
            if reg.period_params == ("period",):
                params["period"] = spec.period
            elif not reg.period_params:
                self.warnings.append(
                    f"{where}: {spec.type} takes no period; ignored period {spec.period}"
                )
            else:
                self.errors.append(
                    f"{where}: {spec.type} has parameters {list(reg.period_params)}, "
                    f"a single period {spec.period} is ambiguous"
                )
                return None
        for p in reg.period_params:
            if p not in params:
                if p == "period" and spec.type in DEFAULT_PERIODS:
                    params[p] = DEFAULT_PERIODS[spec.type]
                    self.defaults.append(
                        f"{where}: {spec.type} period {params[p]} (not stated; common default)"
                    )
                elif p in reg.defaults:
                    params[p] = reg.defaults[p]
                    self.defaults.append(
                        f"{where}: {spec.type}.{p}={reg.defaults[p]} (library default)"
                    )
                else:
                    self.errors.append(f"{where}: {spec.type} needs '{p}' (not stated)")
                    return None
        for p, v in reg.defaults.items():
            if p not in params and p not in reg.period_params:
                params[p] = v
                self.defaults.append(f"{where}: {spec.type}.{p}={v} (library default)")
        parts = [spec.type.lower()] + [
            re.sub(r"[^a-z0-9]", "", str(params[k]).lower()) for k in sorted(params)
        ]
        if spec.source != "close":
            parts.append(spec.source)
        if spec.timeframe is not None:
            parts.append(spec.timeframe)
        iid = "_".join(p for p in parts if p)
        if iid not in self.indicators:
            entry: dict[str, Any] = {"type": spec.type, "params": params}
            if spec.source != "close":
                entry["source"] = spec.source
            if spec.timeframe is not None:
                entry["timeframe"] = spec.timeframe
            self.indicators[iid] = entry
        return iid

    def indicator_field(self, spec: NLIndicator, where: str) -> str | None:
        outputs = OUTPUTS[spec.type]
        if spec.output is None:
            if "value" in outputs:
                return "value"
            self.errors.append(
                f"{where}: {spec.type} has outputs {list(outputs)}; which one is not stated"
            )
            return None
        if spec.output not in outputs:
            self.errors.append(
                f"{where}: {spec.type} has no output '{spec.output}' (outputs: {list(outputs)})"
            )
            return None
        return spec.output

    # --- operands / conditions ----------------------------------------------------------

    def operand(self, op: NLOperand, where: str) -> dict[str, Any] | None:
        if op.kind == "number":
            return {"kind": "const", "value": op.number}
        if op.kind == "price":
            return {"kind": "price", "field": op.price}
        assert op.indicator is not None
        iid = self.indicator_id(op.indicator, where)
        fld = self.indicator_field(op.indicator, where)
        if iid is None or fld is None:
            return None
        ref: dict[str, Any] = {"kind": "indicator", "id": iid}
        if fld != "value":
            ref["field"] = fld
        return ref

    def condition(self, c: NLCondition, where: str) -> dict[str, Any] | None:
        left = self.operand(c.left, where)
        if left is None:
            return None
        if c.comparison in ("crosses_above", "crosses_below"):
            assert c.right is not None
            right = self.operand(c.right, where)
            if right is None:
                return None
            return {"kind": "cross", "left": left, "direction": c.comparison, "right": right}
        if c.comparison == "between":
            assert c.low is not None and c.high is not None
            low, high = self.operand(c.low, where), self.operand(c.high, where)
            if low is None or high is None:
                return None
            return {"kind": "between", "value": left, "low": low, "high": high}
        if c.comparison in ("rising", "falling"):
            bars = c.bars
            if bars is None:
                bars = DEFAULT_SLOPE_BARS
                self.defaults.append(f"{where}: {c.comparison} over {bars} bar (not stated)")
            return {"kind": "slope", "value": left, "direction": c.comparison, "bars": bars}
        assert c.right is not None
        right = self.operand(c.right, where)
        if right is None:
            return None
        return {"kind": "compare", "left": left, "op": COMPARE_OPS[c.comparison], "right": right}

    def condition_set(self, s: NLConditionSet | None, where: str) -> dict[str, Any] | None:
        if s is None:
            return None
        compiled = [
            cond
            for i, c in enumerate(s.conditions)
            if (cond := self.condition(c, f"{where}[{i}] “{c.original_phrase}”")) is not None
        ]
        if not compiled:
            return None
        if len(compiled) == 1:
            return compiled[0]
        return {"kind": "group", "op": s.op, "conditions": compiled}

    # --- levels / sizing ------------------------------------------------------------------

    def atr_id(self, period: int | None, where: str) -> str:
        if period is None:
            period = DEFAULT_ATR_PERIOD
            self.defaults.append(f"{where}: ATR period {period} (not stated)")
        iid = f"atr_{period}"
        self.indicators.setdefault(iid, {"type": "ATR", "params": {"period": period}})
        return iid

    def level(self, lv: NLLevel | None, where: str) -> dict[str, Any] | None:
        if lv is None:
            return None
        if lv.unit == "rr":
            if where != "target":
                self.errors.append(
                    f"{where}: a risk-reward multiple only makes sense for the target"
                )
                return None
            return {"rr_multiple": lv.value}
        if lv.unit == "atr":
            return {
                "unit": "atr",
                "value": lv.value,
                "atr_indicator_id": self.atr_id(lv.atr_period, where),
            }
        return {"unit": lv.unit, "value": lv.value}

    def sizing(self, sz: NLSizing | None) -> dict[str, Any] | None:
        if sz is None:
            return None
        if sz.method in ("fixed_lots", "fixed_quantity"):
            if sz.value != int(sz.value):
                self.errors.append(
                    f"position_sizing: {sz.method} needs a whole number, got {sz.value}"
                )
                return None
            key = "lots" if sz.method == "fixed_lots" else "quantity"
            return {"method": sz.method, key: int(sz.value)}
        key = "capital" if sz.method == "fixed_capital" else "risk_percent"
        return {"method": sz.method, key: sz.value}


def _universe(
    instrument: str, instrument_ids: list[str] | None, defaults: list[str]
) -> dict[str, Any]:
    sym = instrument.strip().upper()
    if sym in INDEX_UNDERLYINGS:
        defaults.append(
            f"universe: {sym} current-month future (an index cannot be traded directly)"
        )
        return {
            "kind": "underlying_future",
            "underlying": sym,
            "contract": {"expiry": "current_month"},
        }
    return {"kind": "instrument", "instrument_ids": list(instrument_ids or [])}


def compile_extraction(
    ex: NLExtraction,
    *,
    market: str,
    instrument: str,
    timeframe: str,
    original_text: str,
    instrument_ids: list[str] | None = None,
) -> CompileResult:
    c = _Compiler()
    if ex.timeframe is not None and ex.timeframe != timeframe:
        c.warnings.append(
            f"timeframe: the description says {ex.timeframe}, the request says {timeframe}; "
            f"using {timeframe}"
        )

    entry_long = c.condition_set(ex.entry_long, "entry.long")
    entry_short = c.condition_set(ex.entry_short, "entry.short")
    exit_long = c.condition_set(ex.exit_long, "exit.long")
    exit_short = c.condition_set(ex.exit_short, "exit.short")

    direction = ex.direction
    if direction is None:
        if entry_long is not None and entry_short is not None:
            direction = "both"
        elif entry_short is not None:
            direction = "short_only"
        else:
            direction = "long_only"
        if entry_long is not None or entry_short is not None:
            c.defaults.append(f"direction: {direction} (inferred from the entry rules given)")

    entry = None
    if entry_long is not None or entry_short is not None:
        entry = {k: v for k, v in (("long", entry_long), ("short", entry_short)) if v is not None}
    exit_ = None
    if exit_long is not None or exit_short is not None:
        exit_ = {k: v for k, v in (("long", exit_long), ("short", exit_short)) if v is not None}

    stop_loss = c.level(ex.stop_loss, "stop_loss")
    target = c.level(ex.target, "target")
    sizing = c.sizing(ex.position_sizing)

    session: dict[str, Any] = {"product": "INTRADAY"}
    if ex.session is not None and ex.session.product is not None:
        session["product"] = ex.session.product
    else:
        c.defaults.append("session.product=INTRADAY (not stated; confirm or change)")
    if ex.session is not None:
        for k in ("trade_start", "no_new_entries_after", "square_off_at"):
            v = getattr(ex.session, k)
            if v is not None:
                session[k] = v

    dsl: dict[str, Any] = {
        "dsl_schema_version": DSL_SCHEMA_VERSION,
        "name": ex.strategy_name,
        "origin": "user_nl",
        "original_text": original_text,
        "language": ex.detected_language,
        "market": market,
        "universe": _universe(instrument, instrument_ids, c.defaults),
        "timeframe": timeframe,
        "session": session,
        "indicators": c.indicators,
        "direction": direction,
        "entry": entry,
        "exit": exit_,
        "stop_loss": stop_loss,
        "target": target,
        "position_sizing": sizing,
    }
    if ex.max_trades_per_day is not None:
        dsl["max_trades_per_day"] = ex.max_trades_per_day
    return CompileResult(dsl=dsl, errors=c.errors, warnings=c.warnings, defaults_applied=c.defaults)
