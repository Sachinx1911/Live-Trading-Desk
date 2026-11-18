"""Filter engine over scanner snapshot rows (Polars). Field names are validated against
the catalogue so a bad filter fails loudly instead of silently matching nothing."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

import polars as pl

FieldType = Literal["number", "percent", "string", "enum", "bool", "date"]

# name -> catalogue entry (label, type, group, unit, description, higher_is_better, values)
FIELDS: dict[str, dict[str, Any]] = {
    "symbol": {"label": "Symbol", "type": "string", "group": "Instrument"},
    "name": {"label": "Name", "type": "string", "group": "Instrument"},
    "segment": {
        "label": "Segment", "type": "enum", "group": "Instrument",
        "values": ["equity", "index", "futures"],
    },
    "underlying": {"label": "Underlying", "type": "string", "group": "Instrument"},
    "expiry": {"label": "Expiry", "type": "date", "group": "Instrument"},
    "lot_size": {"label": "Lot size", "type": "number", "group": "Instrument"},
    "sector": {"label": "Sector", "type": "string", "group": "Instrument",
               "description": "Reserved; populated once a sector master is imported"},
    "last_close": {"label": "Price", "type": "number", "group": "Price", "unit": "INR"},
    "prev_close": {"label": "Prev close", "type": "number", "group": "Price", "unit": "INR"},
    "change_1d_pct": {"label": "Chg 1D %", "type": "percent", "group": "Performance",
                      "higher_is_better": True},
    "change_5d_pct": {"label": "Chg 5D %", "type": "percent", "group": "Performance",
                      "higher_is_better": True},
    "change_20d_pct": {"label": "Chg 20D %", "type": "percent", "group": "Performance",
                       "higher_is_better": True},
    "gap_pct": {"label": "Gap %", "type": "percent", "group": "Performance",
                "description": "Open vs previous close"},
    "volume": {"label": "Volume", "type": "number", "group": "Volume"},
    "avg_volume_20": {"label": "Avg vol 20D", "type": "number", "group": "Volume"},
    "rel_volume": {"label": "Rel volume", "type": "number", "group": "Volume",
                   "description": "Volume / 20-day average"},
    "atr14_pct": {"label": "ATR 14 %", "type": "percent", "group": "Volatility"},
    "rsi14": {"label": "RSI 14", "type": "number", "group": "Technicals"},
    "adx14": {"label": "ADX 14", "type": "number", "group": "Technicals"},
    "ema20": {"label": "EMA 20", "type": "number", "group": "Technicals"},
    "ema50": {"label": "EMA 50", "type": "number", "group": "Technicals"},
    "ema200": {"label": "EMA 200", "type": "number", "group": "Technicals"},
    "ema_alignment": {"label": "EMA alignment", "type": "enum", "group": "Technicals",
                      "values": ["bull", "bear", "mixed"]},
    "dist_52w_high_pct": {"label": "From 52W high %", "type": "percent", "group": "Range",
                          "description": "Negative = below the high"},
    "dist_52w_low_pct": {"label": "From 52W low %", "type": "percent", "group": "Range"},
    "oi": {"label": "OI", "type": "number", "group": "Derivatives"},
    "oi_change_1d_pct": {"label": "OI chg 1D %", "type": "percent", "group": "Derivatives"},
    "regime_trend": {"label": "Regime trend", "type": "enum", "group": "Regime",
                     "values": ["up", "down", "sideways"]},
    "regime_strength": {"label": "Regime strength", "type": "enum", "group": "Regime",
                        "values": ["weak", "moderate", "strong"]},
    "regime_volatility": {"label": "Regime volatility", "type": "enum", "group": "Regime",
                          "values": ["low", "normal", "high"]},
    "regime_structure": {"label": "Regime structure", "type": "enum", "group": "Regime",
                         "values": ["bullish", "bearish", "range"]},
    "bars": {"label": "Daily bars", "type": "number", "group": "Data"},
}  # fmt: skip

DEFAULT_COLUMNS = [
    "symbol",
    "name",
    "segment",
    "last_close",
    "change_1d_pct",
    "volume",
    "rel_volume",
    "rsi14",
    "adx14",
    "atr14_pct",
    "ema_alignment",
    "regime_trend",
]

OPS = ("eq", "ne", "gt", "gte", "lt", "lte", "between", "in", "contains")


class ScanQueryError(ValueError):
    pass


@dataclass(frozen=True)
class Condition:
    field: str
    op: str
    value: Any


@dataclass(frozen=True)
class ScanQuery:
    all: tuple[Condition, ...] = ()
    any: tuple[Condition, ...] = ()
    sort_field: str | None = None
    sort_dir: str = "desc"
    columns: tuple[str, ...] = field(default_factory=lambda: tuple(DEFAULT_COLUMNS))
    offset: int = 0
    limit: int = 100

    @classmethod
    def from_dict(cls, spec: dict[str, Any]) -> ScanQuery:
        filters = spec.get("filters") or {}

        def conds(items: Any) -> tuple[Condition, ...]:
            out = []
            for it in items or []:
                c = Condition(str(it["field"]), str(it["op"]), it.get("value"))
                _validate(c)
                out.append(c)
            return tuple(out)

        sort = spec.get("sort") or {}
        sf = sort.get("field")
        if sf is not None and sf not in FIELDS:
            raise ScanQueryError(f"unknown sort field {sf!r}")
        sd = str(sort.get("dir", "desc")).lower()
        if sd not in ("asc", "desc"):
            raise ScanQueryError("sort.dir must be asc or desc")
        cols = tuple(spec.get("columns") or DEFAULT_COLUMNS)
        for c in cols:
            if c not in FIELDS:
                raise ScanQueryError(f"unknown column {c!r}")
        return cls(
            all=conds(filters.get("all")),
            any=conds(filters.get("any")),
            sort_field=sf,
            sort_dir=sd,
            columns=cols,
            offset=max(int(spec.get("offset", 0)), 0),
            limit=min(max(int(spec.get("limit", 100)), 1), 2000),
        )


def _validate(c: Condition) -> None:
    if c.field not in FIELDS:
        raise ScanQueryError(f"unknown field {c.field!r}")
    if c.op not in OPS:
        raise ScanQueryError(f"unknown op {c.op!r}")
    ftype = FIELDS[c.field]["type"]
    if c.op == "between" and not (isinstance(c.value, list | tuple) and len(c.value) == 2):
        raise ScanQueryError("between needs [low, high]")
    if c.op == "in" and not isinstance(c.value, list | tuple):
        raise ScanQueryError("in needs a list")
    if c.op == "contains" and ftype not in ("string", "enum"):
        raise ScanQueryError("contains works on text fields only")
    if c.op in ("gt", "gte", "lt", "lte") and ftype in ("string", "enum", "bool"):
        raise ScanQueryError(f"{c.op} needs a numeric field")


def _expr(c: Condition) -> pl.Expr:
    col = pl.col(c.field)
    v = c.value
    match c.op:
        case "eq":
            eq: pl.Expr = col.eq(pl.lit(v))
            return eq
        case "ne":
            ne: pl.Expr = col.ne(pl.lit(v))
            return ne
        case "gt":
            return col > float(v)
        case "gte":
            return col >= float(v)
        case "lt":
            return col < float(v)
        case "lte":
            return col <= float(v)
        case "between":
            lo, hi = float(v[0]), float(v[1])
            between: pl.Expr = (col >= lo) & (col <= hi)
            return between
        case "in":
            is_in: pl.Expr = col.is_in(list(v))
            return is_in
        case "contains":
            return col.cast(pl.Utf8).str.to_uppercase().str.contains(str(v).upper(), literal=True)
    raise ScanQueryError(c.op)  # pragma: no cover


def _frame(rows: Sequence[dict[str, Any]]) -> pl.DataFrame:
    if not rows:
        return pl.DataFrame({k: [] for k in FIELDS})
    df = pl.DataFrame(rows, infer_schema_length=None)
    for name, meta in FIELDS.items():
        if name not in df.columns:
            df = df.with_columns(pl.lit(None).alias(name))
        if meta["type"] in ("number", "percent") and not df[name].dtype.is_numeric():
            df = df.with_columns(pl.col(name).cast(pl.Float64, strict=False))
    return df


def apply_query(rows: Sequence[dict[str, Any]], q: ScanQuery) -> tuple[list[dict[str, Any]], int]:
    """Filter, sort and page the snapshot rows. Returns (page rows, total matches)."""
    df = _frame(rows)
    if df.is_empty():
        return [], 0
    mask: pl.Expr | None = None
    for c in q.all:
        e = _expr(c)
        mask = e if mask is None else (mask & e)
    if q.any:
        any_mask: pl.Expr | None = None
        for c in q.any:
            e = _expr(c)
            any_mask = e if any_mask is None else (any_mask | e)
        assert any_mask is not None
        mask = any_mask if mask is None else (mask & any_mask)
    if mask is not None:
        df = df.filter(mask.fill_null(False))
    if q.sort_field:
        df = df.sort(q.sort_field, descending=q.sort_dir == "desc", nulls_last=True)
    total = df.height
    page = df.slice(q.offset, q.limit)
    keep = [c for c in dict.fromkeys(("instrument_id", *q.columns)) if c in page.columns]
    return page.select(keep).to_dicts(), total
