"""Validation rules from spec §9. Structural problems are errors for every status;
completeness and live-readiness are errors only when validating for that target status."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time
from typing import Literal

from strategy.dsl.schema import (
    ArithRef,
    Between,
    Compare,
    Condition,
    ConstRef,
    Cross,
    Group,
    IndicatorRef,
    Label,
    LevelSpec,
    Not,
    Operand,
    OptionRef,
    PriceRef,
    Slope,
    StrategyDocument,
)
from strategy.indicators import OUTPUTS, period_like_params

Target = Literal["draft", "validated", "approved_live"]

SESSION_OPEN = time(9, 15)
SESSION_CLOSE = time(15, 30)
MAX_PRIMARY_PERIOD = 500


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _parse_hhmm(value: str) -> time | None:
    try:
        h, m = value.split(":")
        return time(int(h), int(m))
    except (ValueError, AttributeError):
        return None


class _Walker:
    """Collect operand refs, leaf counts and depth over a condition tree."""

    def __init__(self, doc: StrategyDocument, report: ValidationReport, where: str) -> None:
        self.doc = doc
        self.report = report
        self.where = where
        self.leaves = 0
        self.has_noisy_cross = False
        self.numeric_consts = 0
        self.uses_option_data = False

    def operand(self, op: Operand, depth: int = 0) -> None:
        if isinstance(op, IndicatorRef):
            spec = self.doc.indicators.get(op.id)
            if spec is None:
                self.report.errors.append(f"{self.where}: indicator '{op.id}' is not declared")
            elif op.field not in OUTPUTS[spec.type]:
                self.report.errors.append(
                    f"{self.where}: indicator '{op.id}' ({spec.type}) has no field '{op.field}'"
                )
        elif isinstance(op, ConstRef):
            self.numeric_consts += 1
        elif isinstance(op, ArithRef):
            if depth >= 2:
                self.report.errors.append(f"{self.where}: arithmetic nesting deeper than 2")
            self.operand(op.left, depth + 1)
            self.operand(op.right, depth + 1)
        elif isinstance(op, PriceRef):
            pass
        elif isinstance(op, OptionRef):
            self.uses_option_data = True
            if self.doc.dsl_schema_version == "1.0":
                self.report.errors.append(
                    f"{self.where}: option operands need dsl_schema_version 1.1"
                )

    def condition(self, c: Condition, depth: int = 1) -> None:
        if isinstance(c, Group):
            if depth > 4:
                self.report.errors.append(f"{self.where}: group nesting deeper than 4")
            for child in c.conditions:
                self.condition(child, depth + 1)
            return
        if isinstance(c, Not):
            self.condition(c.condition, depth + 1)
            return
        self.leaves += 1
        if isinstance(c, Compare):
            self.operand(c.left)
            self.operand(c.right)
        elif isinstance(c, Cross):
            self.operand(c.left)
            self.operand(c.right)
            if isinstance(c.left, ConstRef) and isinstance(c.right, ConstRef):
                self.report.errors.append(f"{self.where}: cross between two constants")
            for side in (c.left, c.right):
                if isinstance(side, IndicatorRef):
                    spec = self.doc.indicators.get(side.id)
                    if spec is not None and spec.type == "RSI":
                        self.has_noisy_cross = True
        elif isinstance(c, Between):
            self.operand(c.value)
            self.operand(c.low)
            self.operand(c.high)
        elif isinstance(c, Slope):
            self.operand(c.value)
        elif isinstance(c, Label):
            self.operand(c.value)


def _level(
    doc: StrategyDocument, spec: LevelSpec | None, where: str, report: ValidationReport
) -> None:
    if spec is None:
        return
    unit = spec.unit
    if unit == "atr":
        if spec.value is None:
            report.errors.append(f"{where}: unit=atr requires value")
        if spec.atr_indicator_id is None or spec.atr_indicator_id not in doc.indicators:
            report.errors.append(f"{where}: unit=atr requires a declared atr_indicator_id")
        elif doc.indicators[spec.atr_indicator_id].type != "ATR":
            report.errors.append(f"{where}: atr_indicator_id must reference an ATR indicator")
    elif unit in ("points", "percent"):
        if spec.value is None or spec.value <= 0:
            report.errors.append(f"{where}: unit={unit} requires a positive value")
    elif unit == "structure":
        if spec.structure is None:
            report.errors.append(f"{where}: unit=structure requires structure")
    elif unit == "indicator":
        if spec.indicator_ref is None:
            report.errors.append(f"{where}: unit=indicator requires indicator_ref")
        else:
            _Walker(doc, report, where).operand(spec.indicator_ref)


def validate_document(doc: StrategyDocument, target: Target = "draft") -> ValidationReport:
    r = ValidationReport()

    # --- indicators -------------------------------------------------------------------
    for iid, spec in doc.indicators.items():
        if spec.timeframe is not None and spec.timeframe != doc.timeframe:
            if spec.timeframe not in doc.context_timeframes:
                r.errors.append(
                    f"indicator '{iid}': timeframe {spec.timeframe} not in context_timeframes"
                )
        for p in period_like_params(spec.type, spec.params):
            if (
                spec.timeframe is None or spec.timeframe == doc.timeframe
            ) and p > MAX_PRIMARY_PERIOD:
                r.errors.append(f"indicator '{iid}': period {p} exceeds {MAX_PRIMARY_PERIOD} bars")

    # --- direction vs entry rules ---------------------------------------------------------
    if doc.entry is not None:
        if doc.direction in ("long_only", "both") and doc.entry.long is None:
            r.errors.append("entry.long required for direction " + doc.direction)
        if doc.direction in ("short_only", "both") and doc.entry.short is None:
            r.errors.append("entry.short required for direction " + doc.direction)
        if doc.direction == "long_only" and doc.entry.short is not None:
            r.errors.append("entry.short given but direction is long_only")
        if doc.direction == "short_only" and doc.entry.long is not None:
            r.errors.append("entry.long given but direction is short_only")

    # --- conditions ---------------------------------------------------------------------
    walkers: list[_Walker] = []
    for where, cond in (
        ("entry.long", doc.entry.long if doc.entry else None),
        ("entry.short", doc.entry.short if doc.entry else None),
        ("exit.long", doc.exit.long if doc.exit else None),
        ("exit.short", doc.exit.short if doc.exit else None),
    ):
        if cond is not None:
            w = _Walker(doc, r, where)
            w.condition(cond)
            walkers.append(w)

    # --- session ------------------------------------------------------------------------
    s = doc.session
    close = SESSION_CLOSE
    for name, val in (
        ("trade_start", s.trade_start),
        ("no_new_entries_after", s.no_new_entries_after),
        ("square_off_at", s.square_off_at),
    ):
        if val is not None:
            t = _parse_hhmm(val)
            if t is None:
                r.errors.append(f"session.{name}: not HH:MM")
            elif not (SESSION_OPEN <= t <= close):
                r.errors.append(f"session.{name}: outside exchange session")
    if s.product == "INTRADAY":
        if s.square_off_at is None:
            if target == "draft":
                r.missing_information.append("Product/square-off")
            else:
                r.errors.append("session.square_off_at required for INTRADAY")
        else:
            t = _parse_hhmm(s.square_off_at)
            if t is not None and t >= close:
                r.errors.append("session.square_off_at must be before session close")
    for tf in doc.time_filters:
        a, b = _parse_hhmm(tf.start), _parse_hhmm(tf.end)
        if a is None or b is None or not (SESSION_OPEN <= a < b <= close):
            r.errors.append(f"time_filter {tf.start}-{tf.end}: not a valid in-session window")
    if any(d < 0 or d > 6 for d in s.allowed_weekdays):
        r.errors.append("session.allowed_weekdays: values must be 0..6")

    # --- regime filters -----------------------------------------------------------------
    for rf in doc.regime_filters:
        if rf.source == "adx":
            if rf.indicator_id is None or rf.indicator_id not in doc.indicators:
                r.errors.append("regime_filter adx: indicator_id must reference a declared ADX")
            elif doc.indicators[rf.indicator_id].type != "ADX":
                r.errors.append("regime_filter adx: indicator must be of type ADX")
        if rf.source in ("daily_trend", "regime_label") and not rf.allowed:
            r.errors.append(f"regime_filter {rf.source}: 'allowed' list required")

    # --- levels -------------------------------------------------------------------------
    _level(doc, doc.stop_loss, "stop_loss", r)
    if doc.target is not None:
        if doc.target.rr_multiple is not None and doc.stop_loss is None:
            r.errors.append("target.rr_multiple requires stop_loss")
        if doc.target.unit is not None:
            _level(doc, doc.target, "target", r)
        elif doc.target.rr_multiple is None:
            r.errors.append("target: unit or rr_multiple required")
        if sum(p.close_pct for p in doc.target.partial) > 100:
            r.errors.append("target.partial: close_pct sum exceeds 100")
        for i, pt in enumerate(doc.target.partial):
            _level(doc, pt.at, f"target.partial[{i}]", r)
    if doc.trailing is not None:
        tr = doc.trailing
        if tr.mode == "atr" and (tr.atr_indicator_id not in doc.indicators or tr.value is None):
            r.errors.append("trailing: mode=atr requires value and a declared atr_indicator_id")
        if tr.mode in ("percent", "points") and (tr.value is None or tr.value <= 0):
            r.errors.append(f"trailing: mode={tr.mode} requires a positive value")
        if tr.mode == "indicator" and tr.indicator_ref is None:
            r.errors.append("trailing: mode=indicator requires indicator_ref")
        _level(doc, tr.activate_after, "trailing.activate_after", r)

    # --- sizing -------------------------------------------------------------------------
    ps = doc.position_sizing
    if ps is not None:
        need = {
            "fixed_lots": ps.lots,
            "fixed_quantity": ps.quantity,
            "fixed_capital": ps.capital,
            "risk_percent": ps.risk_percent,
        }[ps.method]
        if need is None:
            r.errors.append(f"position_sizing: method {ps.method} requires its parameter")
        if ps.method == "risk_percent" and doc.stop_loss is None:
            r.errors.append("position_sizing: risk_percent requires stop_loss")

    # --- universe -----------------------------------------------------------------------
    u = doc.universe
    if u.kind == "instrument" and not u.instrument_ids:
        r.errors.append("universe: kind=instrument requires instrument_ids")
    if u.kind in ("underlying_future", "underlying_option") and (
        u.underlying is None or u.contract is None
    ):
        r.errors.append(f"universe: kind={u.kind} requires underlying and contract")
    if (
        u.kind == "underlying_option"
        and u.contract is not None
        and (u.contract.option_type is None or u.contract.strike is None)
    ):
        r.errors.append("universe: underlying_option requires contract.option_type and strike")
    if u.kind == "watchlist" and not u.watchlist_id:
        r.errors.append("universe: kind=watchlist requires watchlist_id")
    if u.kind == "scanner" and not u.scanner_id:
        r.errors.append("universe: kind=scanner requires scanner_id")

    # --- completeness -------------------------------------------------------------------
    missing: list[str] = []
    if doc.entry is None:
        missing.append("Entry condition")
    if doc.exit is None and doc.target is None:
        missing.append("Exit condition")
    if doc.stop_loss is None:
        missing.append("Stop loss")
    if doc.target is None:
        missing.append("Target")
    if doc.position_sizing is None:
        missing.append("Position sizing")
    for m in missing:
        if m in ("Entry condition", "Position sizing", "Exit condition"):
            if target == "draft":
                r.missing_information.append(m)
            else:
                r.errors.append(f"incomplete: {m.lower()} missing")
        elif m not in r.missing_information:
            r.missing_information.append(m)

    # --- live readiness -----------------------------------------------------------------
    if target == "approved_live":
        if doc.stop_loss is None:
            r.errors.append("live: stop_loss required")
        if ps is None or (ps.max_lots is None and ps.max_capital_pct is None):
            r.errors.append("live: position_sizing.max_lots or max_capital_pct required")
        if doc.max_trades_per_day is None:
            r.errors.append("live: max_trades_per_day required")

    # --- warnings -----------------------------------------------------------------------
    tunable = sum(len(period_like_params(s_.type, s_.params)) for s_ in doc.indicators.values())
    tunable += sum(w.numeric_consts for w in walkers)
    if tunable > 3:
        r.warnings.append(f"{tunable} tunable numeric parameters: over-fitting risk")
    for w in walkers:
        if w.where.startswith("entry") and w.leaves > 6:
            r.warnings.append(f"{w.where}: more than 6 leaf conditions")
        if w.has_noisy_cross and doc.entry is not None and doc.entry.confirm_bars == 0:
            r.warnings.append(f"{w.where}: cross on RSI with confirm_bars=0 is noisy")
    if any(w.uses_option_data for w in walkers):
        r.warnings.append(
            "uses option-chain data: bars without a stored chain snapshot give no value "
            "(conditions on them are false), so backtests only trade where chain history exists"
        )
    return r
