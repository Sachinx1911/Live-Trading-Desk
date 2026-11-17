"""Pure parsers for NSE payloads. No I/O, no DB. Input is untrusted; bad rows are skipped
and counted rather than raising, except for structurally unusable files."""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

import polars as pl
from polars._typing import PolarsDataType

# ---------------------------------------------------------------------------------------
# Holidays
# ---------------------------------------------------------------------------------------

_HOLIDAY_DATE_FORMATS = ("%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d")


@dataclass(frozen=True)
class Holiday:
    day: date
    description: str
    segment: str  # CM | FO | ...


def _parse_date_loose(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    v = value.strip()
    for fmt in _HOLIDAY_DATE_FORMATS:
        try:
            return datetime.strptime(v, fmt).date()  # noqa: DTZ007 - date only
        except ValueError:
            continue
    return None


def parse_holidays(
    payload: dict[str, Any], segments: tuple[str, ...] = ("CM", "FO")
) -> list[Holiday]:
    """holiday-master JSON → holidays for the requested segments (deduplicated per segment)."""
    out: list[Holiday] = []
    seen: set[tuple[date, str]] = set()
    for seg in segments:
        rows = payload.get(seg)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            d = _parse_date_loose(row.get("tradingDate"))
            if d is None:
                continue
            desc = str(row.get("description") or "").strip()
            if (d, seg) in seen:
                continue
            seen.add((d, seg))
            out.append(Holiday(d, desc, seg))
    out.sort(key=lambda h: (h.day, h.segment))
    return out


# ---------------------------------------------------------------------------------------
# Bhavcopy (UDiFF CSV inside a zip)
# ---------------------------------------------------------------------------------------


def _read_zip_csv(blob: bytes) -> pl.DataFrame:
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
            if not names:
                raise ValueError("zip contains no csv")
            with zf.open(names[0]) as fh:
                raw = fh.read()
    except zipfile.BadZipFile:
        # Some mirrors serve the CSV uncompressed.
        raw = blob
    return pl.read_csv(io.BytesIO(raw), infer_schema_length=0)  # everything as str, cast later


class _Row:
    """Typed accessor: canonical name → raw string via the resolved column map."""

    def __init__(self, rec: dict[str, Any], cols: dict[str, str | None]) -> None:
        self._rec = rec
        self._cols = cols

    def __call__(self, key: str) -> str | None:
        col = self._cols.get(key)
        if col is None:
            return None
        v = self._rec.get(col)
        return None if v is None else str(v)


def _col(df: pl.DataFrame, *candidates: str) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    return None


def _to_decimal(v: str | None) -> Decimal | None:
    if v is None:
        return None
    s = v.strip().replace(",", "")
    if not s or s in {"-", "NA", "null"}:
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def _to_int(v: str | None) -> int | None:
    d = _to_decimal(v)
    return None if d is None else int(d)


def _parse_iso_date(v: str | None) -> date | None:
    if not v:
        return None
    return _parse_date_loose(v.strip())


def parse_cm_bhavcopy(blob: bytes) -> pl.DataFrame:
    """Cash-market UDiFF bhavcopy → canonical columns. Rows with unparsable prices are dropped."""
    df = _read_zip_csv(blob)
    sym = _col(df, "TckrSymb", "SYMBOL")
    if sym is None:
        raise ValueError("bhavcopy: no symbol column")
    cols: dict[str, str | None] = {
        "symbol": sym,
        "isin": _col(df, "ISIN"),
        "series": _col(df, "SctySrs", "SERIES"),
        "date": _col(df, "TradDt", "DATE1"),
        "open": _col(df, "OpnPric", "OPEN_PRICE"),
        "high": _col(df, "HghPric", "HIGH_PRICE"),
        "low": _col(df, "LwPric", "LOW_PRICE"),
        "close": _col(df, "ClsPric", "CLOSE_PRICE"),
        "last": _col(df, "LastPric", "LAST_PRICE"),
        "prev_close": _col(df, "PrvsClsgPric", "PREV_CLOSE"),
        "volume": _col(df, "TtlTradgVol", "TTL_TRD_QNTY"),
        "turnover": _col(df, "TtlTrfVal", "TURNOVER_LACS"),
        "trades": _col(df, "TtlNbOfTxsExctd", "NO_OF_TRADES"),
    }
    rows: list[dict[str, Any]] = []
    for rec in df.iter_rows(named=True):
        get = _Row(rec, cols)
        d = _parse_iso_date(get("date"))
        o, h, lo, c = (_to_decimal(get(k)) for k in ("open", "high", "low", "close"))
        if d is None or None in (o, h, lo, c):
            continue
        rows.append(
            {
                "symbol": str(get("symbol") or "").strip(),
                "isin": (str(get("isin")).strip() or None) if get("isin") else None,
                "series": (str(get("series")).strip() or None) if get("series") else None,
                "date": d,
                "open": o,
                "high": h,
                "low": lo,
                "close": c,
                "last": _to_decimal(get("last")),
                "prev_close": _to_decimal(get("prev_close")),
                "volume": _to_int(get("volume")) or 0,
                "turnover": _to_decimal(get("turnover")),
                "trades": _to_int(get("trades")),
            }
        )
    schema: dict[str, PolarsDataType] = {
        "symbol": pl.Utf8,
        "isin": pl.Utf8,
        "series": pl.Utf8,
        "date": pl.Date,
        "open": pl.Decimal(18, 4),
        "high": pl.Decimal(18, 4),
        "low": pl.Decimal(18, 4),
        "close": pl.Decimal(18, 4),
        "last": pl.Decimal(18, 4),
        "prev_close": pl.Decimal(18, 4),
        "volume": pl.Int64,
        "turnover": pl.Decimal(22, 4),
        "trades": pl.Int64,
    }
    return pl.DataFrame(rows, schema=schema, orient="row") if rows else pl.DataFrame(schema=schema)


def parse_fo_bhavcopy(blob: bytes) -> pl.DataFrame:
    """F&O UDiFF bhavcopy → canonical columns.

    instrument_type is one of FUTIDX, FUTSTK, OPTIDX, OPTSTK."""
    df = _read_zip_csv(blob)
    sym = _col(df, "TckrSymb", "SYMBOL")
    if sym is None:
        raise ValueError("fo bhavcopy: no symbol column")
    cols: dict[str, str | None] = {
        "symbol": sym,
        "instrument_type": _col(df, "FinInstrmTp", "INSTRUMENT"),
        "expiry": _col(df, "XpryDt", "EXPIRY_DT"),
        "strike": _col(df, "StrkPric", "STRIKE_PR"),
        "option_type": _col(df, "OptnTp", "OPTION_TYP"),
        "date": _col(df, "TradDt", "TIMESTAMP"),
        "open": _col(df, "OpnPric", "OPEN"),
        "high": _col(df, "HghPric", "HIGH"),
        "low": _col(df, "LwPric", "LOW"),
        "close": _col(df, "ClsPric", "CLOSE"),
        "volume": _col(df, "TtlTradgVol", "CONTRACTS"),
        "oi": _col(df, "OpnIntrst", "OPEN_INT"),
        "oi_change": _col(df, "ChngInOpnIntrst", "CHG_IN_OI"),
        "lot_size": _col(df, "NewBrdLotQty", "LOT_SIZE"),
    }
    rows: list[dict[str, Any]] = []
    for rec in df.iter_rows(named=True):
        get = _Row(rec, cols)
        d = _parse_iso_date(get("date"))
        exp = _parse_iso_date(get("expiry"))
        itype = str(get("instrument_type") or "").strip().upper()
        if d is None or exp is None or itype not in {"FUTIDX", "FUTSTK", "OPTIDX", "OPTSTK"}:
            continue
        o, h, lo, c = (_to_decimal(get(k)) for k in ("open", "high", "low", "close"))
        if None in (o, h, lo, c):
            continue
        otype = str(get("option_type") or "").strip().upper() or None
        rows.append(
            {
                "symbol": str(get("symbol") or "").strip(),
                "instrument_type": itype,
                "expiry": exp,
                "strike": _to_decimal(get("strike")) if itype.startswith("OPT") else None,
                "option_type": otype if otype in {"CE", "PE"} else None,
                "date": d,
                "open": o,
                "high": h,
                "low": lo,
                "close": c,
                "volume": _to_int(get("volume")) or 0,
                "oi": _to_int(get("oi")),
                "oi_change": _to_int(get("oi_change")),
                "lot_size": _to_int(get("lot_size")),
            }
        )
    schema: dict[str, PolarsDataType] = {
        "symbol": pl.Utf8,
        "instrument_type": pl.Utf8,
        "expiry": pl.Date,
        "strike": pl.Decimal(14, 2),
        "option_type": pl.Utf8,
        "date": pl.Date,
        "open": pl.Decimal(18, 4),
        "high": pl.Decimal(18, 4),
        "low": pl.Decimal(18, 4),
        "close": pl.Decimal(18, 4),
        "volume": pl.Int64,
        "oi": pl.Int64,
        "oi_change": pl.Int64,
        "lot_size": pl.Int64,
    }
    return pl.DataFrame(rows, schema=schema, orient="row") if rows else pl.DataFrame(schema=schema)


# ---------------------------------------------------------------------------------------
# Corporate action subjects
# ---------------------------------------------------------------------------------------

ActionKind = Literal["bonus", "split", "dividend", "rights", "other"]


@dataclass(frozen=True)
class CorporateActionSpec:
    kind: ActionKind
    ratio_num: int | None = None  # bonus: new shares per `ratio_den` held; split: old FV→new FV
    ratio_den: int | None = None
    amount: Decimal | None = None  # dividend per share (INR)
    raw: str = ""


_RE_BONUS = re.compile(r"\bbonus\b[^\d]*(\d+)\s*:\s*(\d+)", re.I)
_RE_SPLIT = re.compile(
    r"(?:split|sub-?division)"  # keyword
    r".*?(?:rs|re|₹)\.?\s*(\d+(?:\.\d+)?)"  # old face value
    r".*?\bto\b"  # separator
    r".*?(?:rs|re|₹)\.?\s*(\d+(?:\.\d+)?)",  # new face value
    re.I | re.S,
)
_RE_DIVIDEND = re.compile(r"dividend[^\d]*?(?:rs\.?|re\.?|₹)?\s*(\d+(?:\.\d+)?)", re.I)
_RE_RIGHTS = re.compile(r"\brights\b[^\d]*(\d+)\s*:\s*(\d+)", re.I)


def parse_corporate_action_subject(subject: str) -> CorporateActionSpec:
    """Free-text NSE 'subject' → structured spec. Unknown shapes become kind='other'."""
    s = (subject or "").strip()
    low = s.lower()
    if "bonus" in low:
        m = _RE_BONUS.search(s)
        if m:
            return CorporateActionSpec("bonus", int(m.group(1)), int(m.group(2)), raw=s)
        return CorporateActionSpec("other", raw=s)
    if "split" in low or "sub-division" in low or "subdivision" in low:
        m = _RE_SPLIT.search(s)
        if m:
            try:
                old_fv, new_fv = Decimal(m.group(1)), Decimal(m.group(2))
            except InvalidOperation:
                return CorporateActionSpec("other", raw=s)
            if new_fv > 0 and old_fv > 0:
                # Normalise to integer ratio old:new (e.g. 10→2 = 5 new shares per 1 old).
                num, den = _ratio(old_fv, new_fv)
                return CorporateActionSpec("split", num, den, raw=s)
        return CorporateActionSpec("other", raw=s)
    if "rights" in low:
        m = _RE_RIGHTS.search(s)
        if m:
            return CorporateActionSpec("rights", int(m.group(1)), int(m.group(2)), raw=s)
        return CorporateActionSpec("other", raw=s)
    if "dividend" in low:
        m = _RE_DIVIDEND.search(s)
        if m:
            try:
                return CorporateActionSpec("dividend", amount=Decimal(m.group(1)), raw=s)
            except InvalidOperation:
                pass
        return CorporateActionSpec("other", raw=s)
    return CorporateActionSpec("other", raw=s)


def _ratio(old_fv: Decimal, new_fv: Decimal) -> tuple[int, int]:
    """old face value → new face value expressed as (old, new) smallest integers."""
    from fractions import Fraction

    f = Fraction(old_fv) / Fraction(new_fv)
    return f.numerator, f.denominator


def adjustment_factor(spec: CorporateActionSpec) -> Decimal | None:
    """Price multiplier applied to pre-ex history (price_adj = price * factor)."""
    if spec.kind == "bonus" and spec.ratio_num and spec.ratio_den:
        return Decimal(spec.ratio_den) / Decimal(spec.ratio_den + spec.ratio_num)
    if spec.kind == "split" and spec.ratio_num and spec.ratio_den:
        return Decimal(spec.ratio_den) / Decimal(spec.ratio_num)
    return None
