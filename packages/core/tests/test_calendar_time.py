from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from core.calendar import nse_calendar
from core.time import IST, ensure_utc, floor_to, local_to_utc, to_zone

cal = nse_calendar()


def test_weekend_and_holiday_closed() -> None:
    assert not cal.is_trading_day(date(2026, 11, 15))  # Sunday
    assert not cal.is_trading_day(date(2026, 1, 26))  # Republic Day
    assert cal.is_trading_day(date(2026, 11, 17))  # Tuesday


def test_is_open_uses_ist() -> None:
    open_ist = datetime(2026, 11, 17, 9, 15, tzinfo=IST)
    before = datetime(2026, 11, 17, 9, 14, tzinfo=IST)
    after_close = datetime(2026, 11, 17, 15, 30, tzinfo=IST)
    assert cal.is_open(open_ist)
    assert not cal.is_open(before)
    assert not cal.is_open(after_close)


def test_session_bounds_are_utc() -> None:
    bounds = cal.session_bounds_utc(date(2026, 11, 17))
    assert bounds is not None
    o, c = bounds
    assert o.tzinfo == UTC and o.hour == 3 and o.minute == 45
    assert c.hour == 10 and c.minute == 0


def test_square_off_and_next_day() -> None:
    sq = cal.square_off_utc(date(2026, 11, 17))
    assert sq is not None and to_zone(sq, IST).time() == time(15, 20)
    assert cal.next_trading_day(date(2026, 11, 13)) == date(2026, 11, 16)  # Fri -> Mon


def test_ensure_utc_rejects_naive() -> None:
    with pytest.raises(ValueError):
        ensure_utc(datetime(2026, 1, 1))


def test_local_to_utc_and_floor() -> None:
    utc = local_to_utc(datetime(2026, 11, 17, 9, 15), ZoneInfo("Asia/Kolkata"))
    assert utc == datetime(2026, 11, 17, 3, 45, tzinfo=UTC)
    assert floor_to(datetime(2026, 11, 17, 3, 47, 30, tzinfo=UTC), 300) == datetime(
        2026, 11, 17, 3, 45, tzinfo=UTC
    )


def test_ensure_utc_parses_iso_strings() -> None:
    assert ensure_utc("2026-11-17T09:15:00+05:30") == datetime(2026, 11, 17, 3, 45, tzinfo=UTC)
    assert ensure_utc("2026-11-17T03:45:00Z") == datetime(2026, 11, 17, 3, 45, tzinfo=UTC)
    with pytest.raises(ValueError):
        ensure_utc("2026-11-17T03:45:00")
