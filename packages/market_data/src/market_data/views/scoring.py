"""Pure grading of JARVIS's market views (Mark 1 Stage 4.6). No I/O, no LLM.

Rules (from AI-MIOS v1, docs/mark-1-build-plan.md §4.6):

- return_pct = (close_at_due_date - ref_price) / ref_price * 100
- up:       hit if return_pct >= +threshold, else miss
- down:     hit if return_pct <= -threshold, else miss
- sideways: hit if |return_pct| <  threshold, else miss
- void: the due-date daily close is still missing `grace_days` trading days after the due
  date (or the reference price is unusable). A void is neither a hit nor a miss and is left
  out of every hit-rate.

Due date: the observation's anchor session plus `horizon_days` NSE trading days (weekends and
exchange holidays skipped, core.calendar). The anchor is the IST date of the observation if
that is a trading day, else the previous trading day; so a view stated on a Saturday with a
1-day horizon is graded on Monday's close, and the graded close is always after the moment
the view was stated.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from core.calendar import ExchangeCalendar

Direction = Literal["up", "down", "sideways"]
Outcome = Literal["hit", "miss", "void"]

DIRECTIONS: tuple[Direction, ...] = ("up", "down", "sideways")
DEFAULT_THRESHOLD_PCT = Decimal("1.0")  # AI-MIOS v1 used ±1 %
DEFAULT_GRACE_DAYS = 3  # trading days after the due date before a missing close is "void"

# Confidence bands for the calibration view ("is high confidence really more accurate?").
# Lower bound inclusive, upper exclusive, except the last band which includes 1.0.
CONFIDENCE_BANDS: tuple[tuple[str, Decimal, Decimal], ...] = (
    ("0-0.5", Decimal("0"), Decimal("0.5")),
    ("0.5-0.7", Decimal("0.5"), Decimal("0.7")),
    ("0.7-0.85", Decimal("0.7"), Decimal("0.85")),
    ("0.85-1", Decimal("0.85"), Decimal("1")),
)

# Horizon buckets in trading days (inclusive upper bounds).
HORIZON_BUCKETS: tuple[tuple[str, int, int], ...] = (
    ("1d", 1, 1),
    ("2-5d", 2, 5),
    ("6-20d", 6, 20),
    ("21-60d", 21, 60),
    ("61-250d", 61, 250),
)


@dataclass(frozen=True)
class Grade:
    outcome: Outcome
    return_pct: Decimal | None


def return_pct(ref_price: Decimal, close: Decimal) -> Decimal:
    if ref_price <= 0:
        raise ValueError("ref_price must be positive")
    return (close - ref_price) / ref_price * 100


def grade(
    direction: Direction, ref_price: Decimal, close: Decimal, threshold_pct: Decimal
) -> Grade:
    """Hit or miss for a view whose due-date close is known. `threshold_pct` must be > 0."""
    if threshold_pct <= 0:
        raise ValueError("threshold_pct must be positive")
    if direction not in DIRECTIONS:
        raise ValueError(f"unknown direction {direction!r}")
    if ref_price <= 0:
        return Grade("void", None)
    r = return_pct(ref_price, close)
    if direction == "up":
        hit = r >= threshold_pct
    elif direction == "down":
        hit = r <= -threshold_pct
    else:
        hit = abs(r) < threshold_pct
    return Grade("hit" if hit else "miss", r)


def confidence_band(confidence: Decimal | float) -> str:
    c = Decimal(str(confidence))
    if c < 0 or c > 1:
        raise ValueError("confidence must be within 0..1")
    for name, lo, hi in CONFIDENCE_BANDS:
        if lo <= c < hi:
            return name
    return CONFIDENCE_BANDS[-1][0]  # exactly 1.0


def horizon_bucket(horizon_days: int) -> str:
    for name, lo, hi in HORIZON_BUCKETS:
        if lo <= horizon_days <= hi:
            return name
    raise ValueError("horizon_days must be within 1..250")


# ----------------------------------------------------------------- trading-day arithmetic
def add_trading_days(cal: ExchangeCalendar, d: date, n: int) -> date:
    """The n-th trading day after `d` (n >= 0; n == 0 returns `d` unchanged)."""
    if n < 0:
        raise ValueError("n must be >= 0")
    out = d
    for _ in range(n):
        out = cal.next_trading_day(out)
    return out


def anchor_date(cal: ExchangeCalendar, ts: datetime) -> date:
    """The session a view is anchored to: its exchange-local date if that is a trading day,
    else the previous trading day."""
    local = cal.local_date(ts)
    return local if cal.is_trading_day(local) else cal.previous_trading_day(local)


def due_date(cal: ExchangeCalendar, ts: datetime, horizon_days: int) -> date:
    if horizon_days < 1:
        raise ValueError("horizon_days must be >= 1")
    return add_trading_days(cal, anchor_date(cal, ts), horizon_days)


def is_matured(cal: ExchangeCalendar, due: date, now: datetime) -> bool:
    """True once the due date's session has closed."""
    bounds = cal.session_bounds_utc(due)
    if bounds is None:  # not a trading day: cannot happen for a computed due date
        return cal.local_date(now) > due
    return now >= bounds[1]


def past_grace(cal: ExchangeCalendar, due: date, now: datetime, grace_days: int) -> bool:
    """True once `grace_days` trading days after the due date have closed too."""
    return is_matured(cal, add_trading_days(cal, due, grace_days), now)
