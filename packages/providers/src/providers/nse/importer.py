"""Write NSE reference data into the DB (ADR-011). Idempotent upserts; counts returned."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import polars as pl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import CorporateAction, Exchange, Instrument, InstrumentHistory, TradingCalendar
from core.db.models._enums import (
    CorporateActionType,
    HistoryAttribute,
    InstrumentType,
    SessionType,
)
from core.models import Candle, Timeframe
from core.time import utcnow
from providers.nse.parse import (
    CorporateActionSpec,
    Holiday,
    adjustment_factor,
    parse_corporate_action_subject,
)

IST = ZoneInfo("Asia/Kolkata")
SOURCE = "nse"


@dataclass
class ImportCounts:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "inserted": self.inserted,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "skipped": self.skipped,
            "notes": self.notes[:20],
        }


async def _nse_exchange(db: AsyncSession) -> Exchange:
    ex = (await db.execute(select(Exchange).where(Exchange.code == "NSE"))).scalar_one_or_none()
    if ex is None:
        raise RuntimeError("NSE exchange row missing; run migrations/seeds first")
    return ex


# -- holidays --------------------------------------------------------------------------


async def import_holidays(db: AsyncSession, holidays: list[Holiday]) -> ImportCounts:
    """Upsert closed days into trading_calendars for NSE. CM and FO holidays are merged:
    a day is a holiday if either segment is closed (a note records which)."""
    counts = ImportCounts()
    ex = await _nse_exchange(db)
    by_day: dict[date, list[Holiday]] = {}
    for h in holidays:
        by_day.setdefault(h.day, []).append(h)
    if not by_day:
        return counts
    existing = {
        row.date: row
        for row in (
            await db.execute(
                select(TradingCalendar).where(
                    TradingCalendar.exchange_id == ex.id,
                    TradingCalendar.date.in_(list(by_day)),
                )
            )
        ).scalars()
    }
    for day, hs in by_day.items():
        note = "; ".join(sorted({f"{h.segment}: {h.description}" for h in hs}))
        row = existing.get(day)
        if row is None:
            db.add(
                TradingCalendar(
                    exchange_id=ex.id,
                    date=day,
                    session_type=SessionType.HOLIDAY,
                    note=note,
                    source=SOURCE,
                )
            )
            counts.inserted += 1
        elif row.session_type != SessionType.HOLIDAY or row.note != note:
            row.session_type = SessionType.HOLIDAY
            row.note = note
            row.source = SOURCE
            counts.updated += 1
        else:
            counts.unchanged += 1
    await db.flush()
    return counts


# -- corporate actions ------------------------------------------------------------------

_KIND_TO_TYPE: dict[str, CorporateActionType] = {
    "bonus": CorporateActionType.BONUS,
    "split": CorporateActionType.SPLIT,
    "dividend": CorporateActionType.DIVIDEND,
    "rights": CorporateActionType.RIGHTS,
}


def _parse_ca_date(v: Any) -> date | None:
    if not isinstance(v, str) or not v.strip():
        return None
    for fmt in ("%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(v.strip(), fmt).date()  # noqa: DTZ007
        except ValueError:
            continue
    return None


async def _equity_ids_by_symbol(db: AsyncSession, symbols: set[str]) -> dict[str, int]:
    if not symbols:
        return {}
    ex = await _nse_exchange(db)
    rows = await db.execute(
        select(Instrument.symbol, Instrument.id).where(
            Instrument.exchange_id == ex.id,
            Instrument.symbol.in_(symbols),
            Instrument.instrument_type.in_([InstrumentType.EQUITY, InstrumentType.ETF]),
        )
    )
    return {sym: iid for sym, iid in rows.all()}


async def import_corporate_actions(db: AsyncSession, rows: list[dict[str, Any]]) -> ImportCounts:
    """Upsert corporate actions (bonus/split/dividend/rights). Rows for symbols we do not
    track, or with kind 'other', are skipped and counted; the raw subject is kept on stored rows."""
    counts = ImportCounts()
    symbols = {str(r.get("symbol") or "").strip() for r in rows}
    symbols.discard("")
    ids = await _equity_ids_by_symbol(db, symbols)
    for r in rows:
        symbol = str(r.get("symbol") or "").strip()
        ex_date = _parse_ca_date(r.get("exDate"))
        iid = ids.get(symbol)
        if not symbol or ex_date is None or iid is None:
            counts.skipped += 1
            continue
        spec: CorporateActionSpec = parse_corporate_action_subject(str(r.get("subject") or ""))
        atype = _KIND_TO_TYPE.get(spec.kind)
        if atype is None:
            counts.skipped += 1
            counts.notes.append(f"{symbol} {ex_date}: unparsed subject {spec.raw[:60]!r}")
            continue
        existing = (
            (
                await db.execute(
                    select(CorporateAction).where(
                        CorporateAction.instrument_id == iid,
                        CorporateAction.ex_date == ex_date,
                        CorporateAction.action_type == atype,
                    )
                )
            )
            .scalars()
            .first()
        )
        values = {
            "record_date": _parse_ca_date(r.get("recDate")),
            "ratio_from": spec.ratio_den if spec.kind in {"bonus", "rights"} else spec.ratio_num,
            "ratio_to": spec.ratio_num if spec.kind in {"bonus", "rights"} else spec.ratio_den,
            "amount": spec.amount,
            "adjustment_factor": adjustment_factor(spec),
        }
        if existing is None:
            db.add(
                CorporateAction(
                    instrument_id=iid,
                    action_type=atype,
                    ex_date=ex_date,
                    source=SOURCE,
                    raw={"subject": spec.raw, "series": r.get("series")},
                    **values,
                )
            )
            counts.inserted += 1
        else:
            changed = False
            for k, v in values.items():
                if getattr(existing, k) != v:
                    setattr(existing, k, v)
                    changed = True
            if changed:
                existing.source = SOURCE
                counts.updated += 1
            else:
                counts.unchanged += 1
    await db.flush()
    return counts


# -- lot sizes from the F&O bhavcopy --------------------------------------------------------


async def import_fo_lot_sizes(db: AsyncSession, trade_date: date, fo: pl.DataFrame) -> ImportCounts:
    """For each underlying symbol in the F&O bhavcopy, record a lot-size change in
    instrument_history when it differs from the latest known value. Matching is on the
    NSE equity/index instrument with that symbol (NIFTY → 'NIFTY' index row, etc.)."""
    counts = ImportCounts()
    if fo.is_empty() or "lot_size" not in fo.columns:
        return counts
    # Current-month futures carry the authoritative lot size; fall back to any row.
    lots = (
        fo.filter(pl.col("lot_size").is_not_null() & (pl.col("lot_size") > 0))
        .sort(["symbol", "expiry"])
        .group_by("symbol", maintain_order=True)
        .agg(pl.col("lot_size").first())
    )
    symbols = {str(s) for s in lots["symbol"].to_list()}
    ex = await _nse_exchange(db)
    rows = await db.execute(
        select(Instrument.symbol, Instrument.id, Instrument.lot_size).where(
            Instrument.exchange_id == ex.id,
            Instrument.symbol.in_(symbols),
            Instrument.instrument_type.in_([InstrumentType.EQUITY, InstrumentType.INDEX]),
        )
    )
    by_symbol = {sym: (iid, lot) for sym, iid, lot in rows.all()}
    for sym, lot in lots.iter_rows():
        hit = by_symbol.get(str(sym))
        if hit is None:
            counts.skipped += 1
            continue
        iid, _ = hit
        latest = (
            (
                await db.execute(
                    select(InstrumentHistory)
                    .where(
                        InstrumentHistory.instrument_id == iid,
                        InstrumentHistory.attribute == HistoryAttribute.LOT_SIZE,
                    )
                    .order_by(InstrumentHistory.effective_from.desc(), InstrumentHistory.id.desc())
                )
            )
            .scalars()
            .first()
        )
        new_value = str(int(lot))
        if latest is not None and latest.new_value == new_value:
            counts.unchanged += 1
            continue
        if latest is not None and latest.effective_from > trade_date:
            counts.skipped += 1  # never rewrite history from an older file
            continue
        db.add(
            InstrumentHistory(
                instrument_id=iid,
                attribute=HistoryAttribute.LOT_SIZE,
                old_value=latest.new_value if latest is not None else None,
                new_value=new_value,
                effective_from=trade_date,
                source=f"{SOURCE}:fo_bhavcopy",
            )
        )
        counts.inserted += 1
    await db.flush()
    return counts


# -- bhavcopy → canonical daily candles -------------------------------------------------------


def bhavcopy_to_candles(
    cm: pl.DataFrame,
    instrument_id_by_symbol: dict[str, int],
    *,
    provider_id: str = "import",
    series: tuple[str, ...] = ("EQ", "BE", "BZ"),
) -> list[Candle]:
    """Cash bhavcopy rows → D1 candles (ts = 09:15 IST of the trade date, in UTC).
    Symbols without an instrument id are ignored; the caller decides what to do about them."""
    out: list[Candle] = []
    now = utcnow()
    for rec in cm.iter_rows(named=True):
        if rec.get("series") and rec["series"] not in series:
            continue
        iid = instrument_id_by_symbol.get(rec["symbol"])
        if iid is None:
            continue
        d: date = rec["date"]
        ts = datetime.combine(d, time(9, 15), tzinfo=IST)
        o, h, lo, c = (Decimal(str(rec[k])) for k in ("open", "high", "low", "close"))
        # Bhavcopy occasionally has close outside [low, high] on illiquid series; clamp.
        lo, h = min(lo, o, c), max(h, o, c)
        out.append(
            Candle(
                instrument_id=iid,
                timeframe=Timeframe.D1,
                ts=ts,
                open=o,
                high=h,
                low=lo,
                close=c,
                volume=int(rec.get("volume") or 0),
                trade_count=rec.get("trades"),
                provider_id=provider_id,
                provider_ts=ts,
                received_at=now,
                is_demo=False,
            )
        )
    return out
