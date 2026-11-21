"""OI change between two moments of one trading day (Mark 1, package 1.2).

Picks two stored chain snapshots inside the requested window: the first one at or after the
window start, and the last one at or before the window end, both of one provider (series are
never mixed across providers). Per strike it reports call and put OI at both ends and the
change; totals, PCR and spot at both ends. The snapshot times actually used are returned so the
UI can show the gap to the requested times. Nothing is interpolated.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import OptionChainSnapshot as SnapRow
from core.time import IST, ensure_utc
from market_data.repo.chains import oi_totals
from market_data.strike_series import opening_oi


@dataclass(frozen=True)
class StrikeChange:
    strike: Decimal
    call_oi_from: int | None
    call_oi_to: int | None
    put_oi_from: int | None
    put_oi_to: int | None

    @property
    def call_change(self) -> int | None:
        if self.call_oi_from is None or self.call_oi_to is None:
            return None
        return self.call_oi_to - self.call_oi_from

    @property
    def put_change(self) -> int | None:
        if self.put_oi_from is None or self.put_oi_to is None:
            return None
        return self.put_oi_to - self.put_oi_from


def compare_chains(
    rows_from: Sequence[Mapping[str, Any]], rows_to: Sequence[Mapping[str, Any]]
) -> list[StrikeChange]:
    """Per-strike OI at both ends, over the union of strikes, sorted by strike."""
    a = opening_oi(rows_from)
    b = opening_oi(rows_to)
    strikes = sorted({k[0] for k in a} | {k[0] for k in b})
    return [
        StrikeChange(
            strike=s,
            call_oi_from=a.get((s, "CE")),
            call_oi_to=b.get((s, "CE")),
            put_oi_from=a.get((s, "PE")),
            put_oi_to=b.get((s, "PE")),
        )
        for s in strikes
    ]


def pcr(rows: Sequence[Mapping[str, Any]]) -> Decimal | None:
    """Total put OI / total call OI of one snapshot; None when there is no call OI."""
    put, call = oi_totals([dict(r) for r in rows])
    if call <= 0:
        return None
    return (Decimal(put) / Decimal(call)).quantize(Decimal("0.0001"))


@dataclass(frozen=True)
class SnapshotPair:
    start: SnapRow
    end: SnapRow


def ist_day_bounds(day: date) -> tuple[datetime, datetime]:
    start = ensure_utc(datetime.combine(day, time.min, tzinfo=IST))
    return start, start + timedelta(days=1)


async def snapshot_pair(
    session: AsyncSession,
    underlying_id: int,
    expiry: date,
    provider_db_id: int,
    start: datetime,
    end: datetime,
) -> SnapshotPair | None:
    """First non-empty snapshot at or after `start` and last at or before `end`, both inside
    [start, end], for the contracts expiring on the IST date `expiry`. None when the window
    holds no snapshot."""
    start, end = ensure_utc(start), ensure_utc(end)
    exp_lo, exp_hi = ist_day_bounds(expiry)
    base = select(SnapRow).where(
        SnapRow.underlying_instrument_id == underlying_id,
        SnapRow.expiry >= exp_lo,
        SnapRow.expiry < exp_hi,
        SnapRow.provider_id == provider_db_id,
        SnapRow.row_count > 0,
        SnapRow.ts >= start,
        SnapRow.ts <= end,
    )
    first = (await session.execute(base.order_by(SnapRow.ts.asc()).limit(1))).scalar_one_or_none()
    if first is None:
        return None
    last = (await session.execute(base.order_by(SnapRow.ts.desc()).limit(1))).scalar_one()
    return SnapshotPair(first, last)


async def expiries_on_day(
    session: AsyncSession, underlying_id: int, provider_db_id: int, day: date
) -> list[date]:
    """IST expiry dates that have at least one non-empty snapshot on the IST date `day`."""
    lo, hi = ist_day_bounds(day)
    q = (
        select(SnapRow.expiry)
        .where(
            SnapRow.underlying_instrument_id == underlying_id,
            SnapRow.provider_id == provider_db_id,
            SnapRow.row_count > 0,
            SnapRow.ts >= lo,
            SnapRow.ts < hi,
        )
        .distinct()
    )
    days = {ensure_utc(e).astimezone(IST).date() for (e,) in (await session.execute(q)).all()}
    return sorted(days)
