"""Per-strike OI and Greeks series derived from option-chain snapshots (Mark 1, package 1.1).

`option_chain_snapshots` (raw, append-only) keeps each chain as one JSONB document. This module
spreads every snapshot into one row per strike and side in `option_strike_series`, adding the
OI change since the day's opening snapshot. The derived table can always be rebuilt from raw
(`rebuild_strike_series`), so writes are upserts.

Opening baseline: the first non-empty snapshot of the same underlying, expiry and provider at or
after 09:15 IST on the snapshot's IST date. Before that time, or when no baseline exists, the
change is null; it is never guessed.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import OptionChainSnapshot as SnapRow
from core.db.models import OptionStrikeSeries as SeriesRow
from core.models import OptionChainSnapshot
from core.time import IST, ensure_utc
from market_data.repo._lookup import provider_id as provider_db_id

MARKET_OPEN_IST = time(9, 15)
SIDES = ("CE", "PE")

StrikeKey = tuple[Decimal, str]


@dataclass(frozen=True)
class StrikePoint:
    strike: Decimal
    option_type: str
    oi: int | None
    oi_change_from_open: int | None
    ltp: Decimal | None
    volume: int | None
    iv: Decimal | None
    delta: Decimal | None
    gamma: Decimal | None
    theta: Decimal | None
    vega: Decimal | None


def _dec(v: Any) -> Decimal | None:
    if v is None or isinstance(v, bool):
        return None
    try:
        d = Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None
    return d if d.is_finite() else None


def _int(v: Any) -> int | None:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    d = _dec(v)
    return int(d) if d is not None and d == d.to_integral_value() else None


def _key(row: Mapping[str, Any]) -> StrikeKey | None:
    strike = _dec(row.get("strike"))
    side = row.get("option_type")
    if strike is None or side not in SIDES:
        return None
    return (strike, str(side))


def opening_oi(rows: Sequence[Mapping[str, Any]]) -> dict[StrikeKey, int]:
    """OI per (strike, side) of the baseline snapshot; strikes without an OI are left out."""
    out: dict[StrikeKey, int] = {}
    for r in rows:
        k = _key(r)
        oi = _int(r.get("oi"))
        if k is not None and oi is not None:
            out[k] = oi
    return out


def derive_points(
    rows: Sequence[Mapping[str, Any]], baseline: Mapping[StrikeKey, int] | None
) -> list[StrikePoint]:
    """One point per valid (strike, side) row of a snapshot. Rows without a usable strike or
    side are skipped; a later duplicate of the same strike and side replaces the earlier one.
    `baseline` None means no opening snapshot: every change is null."""
    points: dict[StrikeKey, StrikePoint] = {}
    for r in rows:
        k = _key(r)
        if k is None:
            continue
        oi = _int(r.get("oi"))
        base = baseline.get(k) if baseline is not None else None
        change = oi - base if oi is not None and base is not None else None
        points[k] = StrikePoint(
            strike=k[0],
            option_type=k[1],
            oi=oi,
            oi_change_from_open=change,
            ltp=_dec(r.get("ltp")),
            volume=_int(r.get("volume")),
            iv=_dec(r.get("iv")),
            delta=_dec(r.get("delta")),
            gamma=_dec(r.get("gamma")),
            theta=_dec(r.get("theta")),
            vega=_dec(r.get("vega")),
        )
    return [points[k] for k in sorted(points)]


def day_open_utc(ts: datetime) -> datetime:
    """09:15 IST on the IST date of `ts`, in UTC (ADR-006: exchange time derived at the edge)."""
    day: date = ensure_utc(ts).astimezone(IST).date()
    return ensure_utc(datetime.combine(day, MARKET_OPEN_IST, tzinfo=IST))


async def _baseline_snapshot(
    session: AsyncSession, underlying_id: int, expiry: datetime, provider_db_id: int, ts: datetime
) -> SnapRow | None:
    opened = day_open_utc(ts)
    if ts < opened:
        return None
    q = (
        select(SnapRow)
        .where(
            SnapRow.underlying_instrument_id == underlying_id,
            SnapRow.expiry == expiry,
            SnapRow.provider_id == provider_db_id,
            SnapRow.row_count > 0,
            SnapRow.ts >= opened,
            SnapRow.ts <= ts,
        )
        .order_by(SnapRow.ts.asc())
        .limit(1)
    )
    return (await session.execute(q)).scalar_one_or_none()


async def write_series_for_snapshot(session: AsyncSession, snap: SnapRow) -> int:
    """Derive and upsert the strike rows of one stored snapshot. Returns rows written."""
    ts = ensure_utc(snap.ts)
    expiry = ensure_utc(snap.expiry)
    base = await _baseline_snapshot(
        session, snap.underlying_instrument_id, expiry, snap.provider_id, ts
    )
    baseline = opening_oi(base.rows) if base is not None else None
    points = derive_points(snap.rows, baseline)
    if not points:
        return 0
    values = [
        {
            "underlying_instrument_id": snap.underlying_instrument_id,
            "expiry": expiry,
            "ts": ts,
            "provider_id": snap.provider_id,
            "strike": p.strike,
            "option_type": p.option_type,
            "oi": p.oi,
            "oi_change_from_open": p.oi_change_from_open,
            "ltp": p.ltp,
            "volume": p.volume,
            "iv": p.iv,
            "delta": p.delta,
            "gamma": p.gamma,
            "theta": p.theta,
            "vega": p.vega,
        }
        for p in points
    ]
    stmt = insert(SeriesRow).values(values)
    keys = ["underlying_instrument_id", "expiry", "strike", "option_type", "ts", "provider_id"]
    stmt = stmt.on_conflict_do_update(
        index_elements=keys,
        set_={c: stmt.excluded[c] for c in values[0] if c not in keys},
    )
    await session.execute(stmt)
    return len(values)


async def write_series_at(
    session: AsyncSession, underlying_id: int, expiry: datetime, ts: datetime, provider_db_id: int
) -> int:
    """Derive the strike rows of the stored snapshot identified by its primary key."""
    snap = await session.get(
        SnapRow, (underlying_id, ensure_utc(expiry), ensure_utc(ts), provider_db_id)
    )
    return 0 if snap is None else await write_series_for_snapshot(session, snap)


async def write_series_for(session: AsyncSession, snap: OptionChainSnapshot) -> int:
    """Derive the strike rows of a canonical snapshot already written with `write_snapshot`."""
    pid = await provider_db_id(session, snap.provider_id)
    return await write_series_at(session, snap.underlying_instrument_id, snap.expiry, snap.ts, pid)


async def rebuild_strike_series(session: AsyncSession, underlying_id: int, day: date) -> int:
    """Replace the derived rows of one IST day for one underlying (all expiries, providers)
    with rows recomputed from the raw snapshots. Returns rows written."""
    start = ensure_utc(datetime.combine(day, time.min, tzinfo=IST))
    end = start + timedelta(days=1)
    await session.execute(
        delete(SeriesRow).where(
            SeriesRow.underlying_instrument_id == underlying_id,
            SeriesRow.ts >= start,
            SeriesRow.ts < end,
        )
    )
    snaps = (
        (
            await session.execute(
                select(SnapRow)
                .where(
                    SnapRow.underlying_instrument_id == underlying_id,
                    SnapRow.ts >= start,
                    SnapRow.ts < end,
                )
                .order_by(SnapRow.ts.asc())
            )
        )
        .scalars()
        .all()
    )
    written = 0
    for s in snaps:
        written += await write_series_for_snapshot(session, s)
    return written
