"""Pure grading of JARVIS's views and NSE trading-day arithmetic (Mark 1 Stage 4.6)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from core.calendar import nse_calendar
from core.time import IST
from market_data.views.report import ViewRow, aggregate
from market_data.views.scoring import (
    CONFIDENCE_BANDS,
    DEFAULT_THRESHOLD_PCT,
    DIRECTIONS,
    add_trading_days,
    anchor_date,
    confidence_band,
    due_date,
    grade,
    horizon_bucket,
    is_matured,
    past_grace,
    return_pct,
)

CAL = nse_calendar()
T = DEFAULT_THRESHOLD_PCT

prices = st.decimals(min_value=Decimal("1"), max_value=Decimal("100000"), places=2)
thresholds = st.decimals(min_value=Decimal("0.05"), max_value=Decimal("10"), places=2)
days = st.dates(min_value=date(2026, 1, 1), max_value=date(2026, 12, 31))


# ----------------------------------------------------------------- grade: examples
@pytest.mark.parametrize(
    ("direction", "close", "outcome"),
    [
        ("up", "101", "hit"),  # exactly +1 % is a hit
        ("up", "100.99", "miss"),
        ("up", "99", "miss"),
        ("down", "99", "hit"),  # exactly -1 % is a hit
        ("down", "99.01", "miss"),
        ("down", "101", "miss"),
        ("sideways", "100.99", "hit"),
        ("sideways", "99.01", "hit"),
        ("sideways", "101", "miss"),  # |r| == threshold is not sideways
        ("sideways", "99", "miss"),
    ],
)
def test_grade_examples(direction: str, close: str, outcome: str) -> None:
    g = grade(direction, Decimal("100"), Decimal(close), T)  # type: ignore[arg-type]
    assert g.outcome == outcome
    assert g.return_pct == (Decimal(close) - 100)


def test_grade_rejects_bad_input() -> None:
    with pytest.raises(ValueError):
        grade("up", Decimal(100), Decimal(101), Decimal(0))
    with pytest.raises(ValueError):
        grade("left", Decimal(100), Decimal(101), T)  # type: ignore[arg-type]
    assert grade("up", Decimal(0), Decimal(101), T).outcome == "void"


# ----------------------------------------------------------------- grade: properties
@settings(max_examples=300)
@given(ref=prices, close=prices, t=thresholds)
def test_grade_matrix(ref: Decimal, close: Decimal, t: Decimal) -> None:
    """Over the full direction x outcome matrix: each outcome happens exactly when the rule
    says, and no move is a hit for both up and down."""
    r = return_pct(ref, close)
    out = {d: grade(d, ref, close, t).outcome for d in DIRECTIONS}
    assert set(out.values()) <= {"hit", "miss"}
    assert (out["up"] == "hit") == (r >= t)
    assert (out["down"] == "hit") == (r <= -t)
    assert (out["sideways"] == "hit") == (abs(r) < t)
    # exactly one of the three directions is right for any move
    assert sum(v == "hit" for v in out.values()) == 1


@given(ref=prices, t=thresholds, k=st.decimals(min_value=Decimal("1"), max_value=Decimal("5")))
def test_grade_each_cell_reachable(ref: Decimal, t: Decimal, k: Decimal) -> None:
    """Every (direction, outcome) cell is reachable: a big rise, a big fall, a flat close."""
    rise = ref * (1 + t * k / 100)
    fall = ref * (1 - t * k / 100) if t * k < 100 else ref / 2
    flat = ref
    assert grade("up", ref, rise, t).outcome == "hit"
    assert grade("up", ref, fall, t).outcome == "miss"
    assert grade("down", ref, fall, t).outcome == "hit"
    assert grade("down", ref, rise, t).outcome == "miss"
    assert grade("sideways", ref, flat, t).outcome == "hit"
    assert grade("sideways", ref, rise, t).outcome == "miss"


@given(ref=prices, close=prices, t=thresholds)
def test_grade_deterministic(ref: Decimal, close: Decimal, t: Decimal) -> None:
    for d in DIRECTIONS:
        assert grade(d, ref, close, t) == grade(d, ref, close, t)


# ----------------------------------------------------------------- trading days
def test_weekend_and_holiday_examples() -> None:
    fri = date(2026, 11, 20)
    assert add_trading_days(CAL, fri, 1) == date(2026, 11, 23)  # Monday
    # 25 Nov 2026 is a holiday (Guru Nanak Jayanti, static list): Tue + 1 = Thu
    assert add_trading_days(CAL, date(2026, 11, 24), 1) == date(2026, 11, 26)
    assert add_trading_days(CAL, fri, 0) == fri
    sat = datetime(2026, 11, 21, 6, 0, tzinfo=UTC)
    assert anchor_date(CAL, sat) == fri
    assert due_date(CAL, sat, 1) == date(2026, 11, 23)
    # 23:00 IST Monday is still Monday; 20:00 UTC Sunday is 01:30 IST Monday
    assert anchor_date(CAL, datetime(2026, 11, 22, 20, 0, tzinfo=UTC)) == date(2026, 11, 23)


@given(d=days, n=st.integers(min_value=0, max_value=60))
def test_add_trading_days_counts_trading_days(d: date, n: int) -> None:
    out = add_trading_days(CAL, d, n)
    between = [d + timedelta(days=i) for i in range(1, (out - d).days + 1)]
    assert sum(CAL.is_trading_day(x) for x in between) == n
    if n:
        assert CAL.is_trading_day(out)
        assert out > d
        assert out.weekday() < 5 and out not in CAL.holidays
    assert add_trading_days(CAL, d, n + 1) == CAL.next_trading_day(out)


@given(d=days, a=st.integers(0, 30), b=st.integers(0, 30))
def test_add_trading_days_composes(d: date, a: int, b: int) -> None:
    start = add_trading_days(CAL, d, 1)  # a trading day
    assert add_trading_days(CAL, add_trading_days(CAL, start, a), b) == add_trading_days(
        CAL, start, a + b
    )


@given(
    ts=st.datetimes(
        min_value=datetime(2026, 1, 1), max_value=datetime(2026, 11, 30), timezones=st.just(UTC)
    ),
    h=st.integers(1, 250),
)
def test_due_date_is_a_trading_day_after_the_view(ts: datetime, h: int) -> None:
    due = due_date(CAL, ts, h)
    assert CAL.is_trading_day(due)
    assert due > ts.astimezone(IST).date()
    close = CAL.session_bounds_utc(due)
    assert close is not None and close[1] > ts  # the graded close is after the statement
    assert due_date(CAL, ts, h + 1) > due


def test_matured_and_grace() -> None:
    due = date(2026, 11, 23)  # Monday, closes 15:30 IST = 10:00 UTC
    assert not is_matured(CAL, due, datetime(2026, 11, 23, 9, 59, tzinfo=UTC))
    assert is_matured(CAL, due, datetime(2026, 11, 23, 10, 0, tzinfo=UTC))
    # grace 2 -> Wed 25 is a holiday, so Thu 26 must close too
    assert not past_grace(CAL, due, datetime(2026, 11, 25, 12, 0, tzinfo=UTC), 2)
    assert past_grace(CAL, due, datetime(2026, 11, 26, 10, 0, tzinfo=UTC), 2)
    assert past_grace(CAL, due, datetime(2026, 11, 23, 10, 0, tzinfo=UTC), 0)


# ----------------------------------------------------------------- bands and buckets
@given(c=st.decimals(min_value=0, max_value=1, places=3))
def test_confidence_band_total(c: Decimal) -> None:
    name = confidence_band(c)
    lo, hi = next((b[1], b[2]) for b in CONFIDENCE_BANDS if b[0] == name)
    assert lo <= c and (c < hi or c == 1)


def test_bands_and_buckets_edges() -> None:
    assert [confidence_band(Decimal(x)) for x in ("0", "0.5", "0.7", "0.85", "1")] == [
        "0-0.5",
        "0.5-0.7",
        "0.7-0.85",
        "0.85-1",
        "0.85-1",
    ]
    assert [horizon_bucket(x) for x in (1, 2, 5, 6, 20, 21, 60, 61, 250)] == [
        "1d",
        "2-5d",
        "2-5d",
        "6-20d",
        "6-20d",
        "21-60d",
        "21-60d",
        "61-250d",
        "61-250d",
    ]
    with pytest.raises(ValueError):
        horizon_bucket(251)
    with pytest.raises(ValueError):
        confidence_band(Decimal("1.01"))


# ----------------------------------------------------------------- aggregation
def _row(i: int, status: str, conf: str, h: int = 1, sym: str = "NIFTY") -> ViewRow:
    ts = datetime(2026, 11, 2, 5, 0, tzinfo=UTC)
    return ViewRow(
        id=i,
        ts=ts,
        caller="jarvis",
        mode="jarvis",
        instrument_id=1,
        symbol=sym,
        direction="up",
        horizon_days=h,
        confidence=Decimal(conf),
        invalidation=None,
        invalidation_price=None,
        statement=None,
        ref_price=Decimal(100),
        ref_source="upstox:quote",
        ref_freshness="live",
        ref_ts=ts,
        tool_call_id=None,
        due_date=date(2026, 11, 3),
        status=status,  # type: ignore[arg-type]
        close_price=None,
        return_pct=None,
        threshold_pct=None,
        scored_at=None,
        void_reason=None,
    )


def test_aggregate_excludes_pending_and_void_from_hit_rate() -> None:
    rows = [
        _row(1, "hit", "0.9"),
        _row(2, "miss", "0.9"),
        _row(3, "hit", "0.9"),
        _row(4, "void", "0.6"),
        _row(5, "pending", "0.6", h=10, sym="BANKNIFTY"),
    ]
    a = aggregate(rows)
    assert (a.overall.total, a.overall.hits, a.overall.misses) == (5, 2, 1)
    assert (a.overall.voids, a.overall.pending) == (1, 1)
    assert a.overall.hit_rate == pytest.approx(2 / 3)
    assert a.overall.mean_confidence == pytest.approx(0.9)
    bands = {g.key: g for g in a.by_confidence}
    assert list(bands) == [b[0] for b in CONFIDENCE_BANDS]  # every band shown, even empty
    assert bands["0.85-1"].hit_rate == pytest.approx(2 / 3)
    assert bands["0.5-0.7"].hit_rate is None and bands["0.5-0.7"].total == 2
    assert [g.key for g in a.by_instrument] == ["BANKNIFTY", "NIFTY"]
    assert aggregate([]).overall.hit_rate is None
