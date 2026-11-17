"""Time utilities. Rule (ADR-006): everything stored and passed around is aware UTC.
Exchange-local time only at the edges (display, session rules)."""

from __future__ import annotations

from datetime import UTC, datetime, tzinfo
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def utcnow() -> datetime:
    return datetime.now(UTC)


def ensure_utc(value: datetime | str) -> datetime:
    """Return an aware UTC datetime. Accepts ISO-8601 strings (JSON round-trips).
    Naive input is rejected: callers must know the zone."""
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("naive datetime not allowed; attach a timezone first")
    return value.astimezone(UTC)


def to_zone(value: datetime, zone: tzinfo) -> datetime:
    return ensure_utc(value).astimezone(zone)


def local_to_utc(local: datetime, zone: tzinfo) -> datetime:
    """Interpret a naive wall-clock datetime in `zone` and convert to UTC."""
    if local.tzinfo is not None:
        return ensure_utc(local)
    return local.replace(tzinfo=zone).astimezone(UTC)


def floor_to(value: datetime, seconds: int) -> datetime:
    """Floor a UTC datetime to a multiple of `seconds` since the epoch (bar open time)."""
    v = ensure_utc(value)
    epoch = int(v.timestamp())
    return datetime.fromtimestamp(epoch - epoch % seconds, tz=UTC)
