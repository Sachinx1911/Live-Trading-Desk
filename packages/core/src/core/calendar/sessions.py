"""Exchange trading calendars and session rules.

Holidays come from the `trading_calendars` table in production; this module provides the
rules engine plus a static fallback list so that the calendar works before the DB is seeded.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

from core.time import ensure_utc


class SessionKind(StrEnum):
    REGULAR = "regular"
    PRE_OPEN = "pre_open"
    POST_CLOSE = "post_close"
    SPECIAL = "special"  # e.g. Muhurat, budget-day Saturday
    CLOSED = "closed"


@dataclass(frozen=True)
class Session:
    kind: SessionKind
    open: time
    close: time
    square_off: time | None = None  # broker intraday auto square-off (MIS)
    no_new_entries_after: time | None = None  # platform rule: stop new intraday entries


@dataclass(frozen=True)
class ExchangeCalendar:
    exchange: str
    tz: ZoneInfo
    weekly_holidays: frozenset[int]  # weekday numbers, Monday=0
    holidays: frozenset[date]
    regular: Session
    special_sessions: dict[date, Session] = field(default_factory=dict)

    # -- date level -----------------------------------------------------------------
    def is_trading_day(self, d: date) -> bool:
        if d in self.special_sessions:
            return True
        return d.weekday() not in self.weekly_holidays and d not in self.holidays

    def session_for(self, d: date) -> Session | None:
        if d in self.special_sessions:
            return self.special_sessions[d]
        return self.regular if self.is_trading_day(d) else None

    def next_trading_day(self, d: date) -> date:
        n = d + timedelta(days=1)
        while not self.is_trading_day(n):
            n += timedelta(days=1)
        return n

    def previous_trading_day(self, d: date) -> date:
        p = d - timedelta(days=1)
        while not self.is_trading_day(p):
            p -= timedelta(days=1)
        return p

    # -- instant level -------------------------------------------------------------
    def local_date(self, at: datetime) -> date:
        return ensure_utc(at).astimezone(self.tz).date()

    def is_open(self, at: datetime) -> bool:
        local = ensure_utc(at).astimezone(self.tz)
        s = self.session_for(local.date())
        return s is not None and s.open <= local.time() < s.close

    def session_bounds_utc(self, d: date) -> tuple[datetime, datetime] | None:
        s = self.session_for(d)
        if s is None:
            return None
        o = datetime.combine(d, s.open, tzinfo=self.tz)
        c = datetime.combine(d, s.close, tzinfo=self.tz)
        return ensure_utc(o), ensure_utc(c)

    def square_off_utc(self, d: date) -> datetime | None:
        s = self.session_for(d)
        if s is None or s.square_off is None:
            return None
        return ensure_utc(datetime.combine(d, s.square_off, tzinfo=self.tz))

    def minutes_to_close(self, at: datetime) -> int | None:
        local = ensure_utc(at).astimezone(self.tz)
        s = self.session_for(local.date())
        if s is None:
            return None
        close_dt = datetime.combine(local.date(), s.close, tzinfo=self.tz)
        return int((close_dt - local).total_seconds() // 60)


# NSE static fallback. The DB table is authoritative once seeded (Phase 2).
_NSE_HOLIDAYS_2026: frozenset[date] = frozenset(
    {
        date(2026, 1, 26),  # Republic Day
        date(2026, 2, 17),  # Mahashivratri (indicative)
        date(2026, 3, 3),  # Holi (indicative)
        date(2026, 3, 26),  # Ram Navami (indicative)
        date(2026, 4, 3),  # Good Friday
        date(2026, 4, 14),  # Ambedkar Jayanti
        date(2026, 5, 1),  # Maharashtra Day
        date(2026, 8, 15),  # Independence Day
        date(2026, 10, 2),  # Gandhi Jayanti
        date(2026, 11, 10),  # Diwali Laxmi Pujan (indicative)
        date(2026, 11, 25),  # Guru Nanak Jayanti (indicative)
        date(2026, 12, 25),  # Christmas
    }
)

NSE_REGULAR = Session(
    kind=SessionKind.REGULAR,
    open=time(9, 15),
    close=time(15, 30),
    square_off=time(15, 20),
    no_new_entries_after=time(14, 45),
)


def nse_calendar(holidays: frozenset[date] | None = None) -> ExchangeCalendar:
    """NSE calendar. Pass DB-loaded holidays in production; falls back to the static list."""
    return ExchangeCalendar(
        exchange="NSE",
        tz=ZoneInfo("Asia/Kolkata"),
        weekly_holidays=frozenset({5, 6}),
        holidays=holidays if holidays is not None else _NSE_HOLIDAYS_2026,
        regular=NSE_REGULAR,
    )
