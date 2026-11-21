"""Per-strike option series (Mark 1, 1.1): derivation, invariants, live write == rebuild."""

from __future__ import annotations

import os
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import OptionStrikeSeries as SeriesRow
from core.models import OptionChainRow, OptionChainSnapshot, OptionType
from core.time import IST
from market_data.repo.chains import oi_totals, write_snapshot
from market_data.repo.instruments import get_by_symbol
from market_data.strike_series import (
    day_open_utc,
    derive_points,
    opening_oi,
    rebuild_strike_series,
    write_series_for,
)
from market_data.sync import sync_instrument_master
from providers.fake import FakeMarketDataProvider

# --- pure derivation ----------------------------------------------------------------------


def test_change_from_open_per_strike_and_side() -> None:
    base = opening_oi(
        [
            {"strike": "25000", "option_type": "CE", "oi": 1000},
            {"strike": "25000", "option_type": "PE", "oi": 400},
        ]
    )
    pts = derive_points(
        [
            {"strike": "25000", "option_type": "CE", "oi": 1300, "iv": 12.5, "delta": 0.52},
            {"strike": "25000", "option_type": "PE", "oi": 350},
            {"strike": "25100", "option_type": "CE", "oi": 50},  # not in the baseline
        ],
        base,
    )
    by = {(p.strike, p.option_type): p for p in pts}
    assert by[(Decimal(25000), "CE")].oi_change_from_open == 300
    assert by[(Decimal(25000), "CE")].iv == Decimal("12.5")
    assert by[(Decimal(25000), "CE")].delta == Decimal("0.52")
    assert by[(Decimal(25000), "PE")].oi_change_from_open == -50
    assert by[(Decimal(25100), "CE")].oi_change_from_open is None


def test_no_baseline_means_null_change_and_bad_rows_are_skipped() -> None:
    pts = derive_points(
        [
            {"strike": "25000", "option_type": "CE", "oi": 10},
            {"strike": "25000", "option_type": "XX", "oi": 10},
            {"strike": None, "option_type": "PE", "oi": 10},
            {"strike": "abc", "option_type": "PE"},
            {"strike": "24900", "option_type": "PE", "oi": None, "ltp": "101.5"},
        ],
        None,
    )
    assert [(p.strike, p.option_type) for p in pts] == [
        (Decimal(24900), "PE"),
        (Decimal(25000), "CE"),
    ]
    assert all(p.oi_change_from_open is None for p in pts)
    assert pts[0].oi is None and pts[0].ltp == Decimal("101.5")


def test_day_open_is_0915_ist() -> None:
    ts = datetime(2026, 11, 17, 6, 0, tzinfo=UTC)  # 11:30 IST
    opened = day_open_utc(ts)
    assert opened.astimezone(IST).hour == 9 and opened.astimezone(IST).minute == 15
    assert opened.astimezone(IST).date() == date(2026, 11, 17)


_row = st.fixed_dictionaries(
    {
        "strike": st.integers(min_value=100, max_value=400).map(lambda n: str(n * 50)),
        "option_type": st.sampled_from(["CE", "PE"]),
        "oi": st.one_of(st.none(), st.integers(min_value=0, max_value=10_000_000)),
    }
)


@given(st.lists(_row, max_size=60))
def test_points_preserve_side_totals(rows: list[dict[str, object]]) -> None:
    # Later duplicates replace earlier ones in both views, so compare on the deduplicated chain.
    dedup = {(r["strike"], r["option_type"]): r for r in rows}
    chain = list(dedup.values())
    pts = derive_points(chain, None)
    put = sum(p.oi for p in pts if p.option_type == "PE" and p.oi and p.oi > 0)
    call = sum(p.oi for p in pts if p.option_type == "CE" and p.oi and p.oi > 0)
    assert (put, call) == oi_totals(chain)
    assert len(pts) == len(chain)


@given(st.lists(_row, max_size=60))
def test_baseline_against_itself_is_zero_change(rows: list[dict[str, object]]) -> None:
    pts = derive_points(rows, opening_oi(rows))
    for p in pts:
        assert p.oi_change_from_open == (0 if p.oi is not None else None)


# --- database: live write equals rebuild -------------------------------------------------

needs_db = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL_SYNC"), reason="TEST_DATABASE_URL_SYNC not set"
)
DAY = date(2026, 11, 17)


def _snap(und: int, expiry: datetime, ts: datetime, ce: int, pe: int) -> OptionChainSnapshot:
    rows = tuple(
        OptionChainRow(
            instrument_id=und,
            strike=Decimal(k),
            option_type=side,
            oi=oi + i,
            iv=Decimal("13.2"),
            delta=Decimal("0.5"),
        )
        for i, k in enumerate((24900, 25000, 25100))
        for side, oi in ((OptionType.CE, ce), (OptionType.PE, pe))
    )
    return OptionChainSnapshot(
        provider_id="fake",
        received_at=ts,
        is_demo=True,
        underlying_instrument_id=und,
        expiry=expiry,
        ts=ts,
        underlying_price=Decimal("25010"),
        rows=rows,
    )


async def _all(db: AsyncSession, und: int) -> list[tuple[object, ...]]:
    q = select(SeriesRow).where(SeriesRow.underlying_instrument_id == und)
    rows = (await db.execute(q)).scalars().all()
    return sorted(
        (r.ts, r.expiry, r.strike, r.option_type, r.oi, r.oi_change_from_open, r.iv, r.delta)
        for r in rows
    )


@needs_db
async def test_live_write_matches_rebuild(db: AsyncSession) -> None:
    await sync_instrument_master(FakeMarketDataProvider(seed=5, tick_interval=0, today=DAY), db)
    nifty = await get_by_symbol(db, "NSE", "NIFTY")
    assert nifty is not None
    und = nifty.instrument_id
    expiry = datetime(2026, 11, 25, 10, 0, tzinfo=UTC)
    times = [
        datetime(2026, 11, 17, 3, 30, tzinfo=UTC),  # 09:00 IST, before the open: no change
        datetime(2026, 11, 17, 3, 45, tzinfo=UTC),  # 09:15 IST, the baseline
        datetime(2026, 11, 17, 3, 48, tzinfo=UTC),  # 09:18 IST
    ]
    for ts, (ce, pe) in zip(times, [(900, 800), (1000, 400), (1300, 350)], strict=True):
        snap = _snap(und, expiry, ts, ce, pe)
        await write_snapshot(db, snap)
        assert await write_series_for(db, snap) == 6

    live = await _all(db, und)
    assert len(live) == 18
    pre_open = [r for r in live if r[0] == times[0]]
    assert all(r[5] is None for r in pre_open)
    at_open = [r for r in live if r[0] == times[1]]
    assert all(r[5] == 0 for r in at_open)
    later = {(r[2], r[3]): r[5] for r in live if r[0] == times[2]}
    assert later[(Decimal(25000), "CE")] == 300
    assert later[(Decimal(25000), "PE")] == -50

    assert await rebuild_strike_series(db, und, DAY) == 18
    assert await _all(db, und) == live
