"""OI change between two snapshots (Mark 1, 1.2): per-strike comparison, PCR, snapshot choice."""

from __future__ import annotations

import os
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import OptionChainRow, OptionChainSnapshot, OptionType
from market_data.oi_change import compare_chains, expiries_on_day, pcr, snapshot_pair
from market_data.repo._lookup import provider_id
from market_data.repo.chains import write_snapshot
from market_data.repo.instruments import get_by_symbol
from market_data.sync import sync_instrument_master
from providers.fake import FakeMarketDataProvider


def test_compare_chains_union_of_strikes_and_missing_sides() -> None:
    a = [
        {"strike": "25000", "option_type": "CE", "oi": 1000},
        {"strike": "25000", "option_type": "PE", "oi": 400},
    ]
    b = [
        {"strike": "25000", "option_type": "CE", "oi": 1300},
        {"strike": "25000", "option_type": "PE", "oi": 350},
        {"strike": "25100", "option_type": "CE", "oi": 50},
    ]
    out = {s.strike: s for s in compare_chains(a, b)}
    assert list(out) == [Decimal(25000), Decimal(25100)]
    assert out[Decimal(25000)].call_change == 300
    assert out[Decimal(25000)].put_change == -50
    assert out[Decimal(25100)].call_change is None  # no OI at the start: no change claimed
    assert out[Decimal(25100)].put_oi_to is None


def test_pcr_needs_call_oi() -> None:
    assert pcr([{"option_type": "PE", "oi": 150}, {"option_type": "CE", "oi": 100}]) == Decimal(
        "1.5000"
    )
    assert pcr([{"option_type": "PE", "oi": 150}]) is None
    assert pcr([]) is None


_row = st.fixed_dictionaries(
    {
        "strike": st.integers(min_value=100, max_value=200).map(lambda n: str(n * 50)),
        "option_type": st.sampled_from(["CE", "PE"]),
        "oi": st.integers(min_value=0, max_value=1_000_000),
    }
)


@given(st.lists(_row, max_size=40), st.lists(_row, max_size=40))
def test_totals_equal_sum_of_side_differences(a: list[dict], b: list[dict]) -> None:
    out = compare_chains(a, b)
    # On strikes present at both ends the change is exactly to - from.
    for s in out:
        if s.call_change is not None:
            assert s.call_change == (s.call_oi_to or 0) - (s.call_oi_from or 0)
        if s.put_change is not None:
            assert s.put_change == (s.put_oi_to or 0) - (s.put_oi_from or 0)
    # Comparing a chain with itself never shows a change.
    assert all(
        s.call_change in (0, None) and s.put_change in (0, None) for s in compare_chains(a, a)
    )


needs_db = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL_SYNC"), reason="TEST_DATABASE_URL_SYNC not set"
)
DAY = date(2026, 11, 17)


def _snap(und: int, ts: datetime, ce: int) -> OptionChainSnapshot:
    return OptionChainSnapshot(
        provider_id="fake",
        received_at=ts,
        is_demo=True,
        underlying_instrument_id=und,
        expiry=datetime(2026, 11, 25, 10, 0, tzinfo=UTC),  # 15:30 IST on 25 Nov
        ts=ts,
        underlying_price=Decimal("25000"),
        rows=(
            OptionChainRow(
                instrument_id=und, strike=Decimal(25000), option_type=OptionType.CE, oi=ce
            ),
        ),
    )


@needs_db
async def test_snapshot_pair_picks_first_and_last_inside_window(db: AsyncSession) -> None:
    await sync_instrument_master(FakeMarketDataProvider(seed=5, tick_interval=0, today=DAY), db)
    nifty = await get_by_symbol(db, "NSE", "NIFTY")
    assert nifty is not None
    und = nifty.instrument_id
    times = [datetime(2026, 11, 17, 3, m, tzinfo=UTC) for m in (40, 46, 52, 58)]
    for i, ts in enumerate(times):
        await write_snapshot(db, _snap(und, ts, 1000 + i))
    pid = await provider_id(db, "fake")

    pair = await snapshot_pair(
        db, und, date(2026, 11, 25), pid, datetime(2026, 11, 17, 3, 45, tzinfo=UTC), times[2]
    )
    assert pair is not None
    assert pair.start.ts == times[1] and pair.end.ts == times[2]

    assert (
        await snapshot_pair(
            db,
            und,
            date(2026, 11, 25),
            pid,
            datetime(2026, 11, 17, 5, 0, tzinfo=UTC),
            datetime(2026, 11, 17, 6, 0, tzinfo=UTC),
        )
        is None
    )
    assert await snapshot_pair(db, und, date(2026, 11, 26), pid, times[0], times[3]) is None
    assert await expiries_on_day(db, und, pid, DAY) == [date(2026, 11, 25)]
    assert await expiries_on_day(db, und, pid, date(2026, 11, 18)) == []


@needs_db
async def test_chain_oi_history_matches_oi_totals_and_picks_nearest_expiry(
    db: AsyncSession,
) -> None:
    from market_data.repo.chains import chain_oi_history, oi_totals

    await sync_instrument_master(FakeMarketDataProvider(seed=5, tick_interval=0, today=DAY), db)
    nifty = await get_by_symbol(db, "NSE", "NIFTY")
    assert nifty is not None
    und = nifty.instrument_id
    ts = datetime(2026, 11, 17, 4, 0, tzinfo=UTC)
    near = datetime(2026, 11, 20, 10, 0, tzinfo=UTC)
    far = datetime(2026, 11, 27, 10, 0, tzinfo=UTC)
    rows = (
        OptionChainRow(instrument_id=und, strike=Decimal(25000), option_type=OptionType.CE, oi=600),
        OptionChainRow(instrument_id=und, strike=Decimal(25000), option_type=OptionType.PE, oi=900),
        OptionChainRow(instrument_id=und, strike=Decimal(25100), option_type=OptionType.PE, oi=0),
        OptionChainRow(instrument_id=und, strike=Decimal(25100), option_type=OptionType.CE),
    )
    for exp, factor in ((near, 1), (far, 10)):
        snap = _snap(und, ts, 0).model_copy(
            update={
                "expiry": exp,
                "rows": tuple(r.model_copy(update={"oi": (r.oi or 0) * factor}) for r in rows),
            }
        )
        await write_snapshot(db, snap)

    hist = await chain_oi_history(db, und, ts - timedelta(hours=1), ts, "fake")
    assert len(hist) == 1
    p = hist[0]
    assert p.expiry == near
    expected = oi_totals([r.model_dump(mode="json") for r in rows])
    assert (p.put_oi, p.call_oi) == expected == (900, 600)
    assert await chain_oi_history(db, und, ts - timedelta(hours=1), ts, "upstox") == []
