"""Data quality: missing-minute gaps and duplicate bars, per instrument and session day."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from core.calendar import ExchangeCalendar
from core.db.models import DataQualityCheck
from core.db.models._enums import QualityCheckType, Severity
from core.models import Candle, Timeframe
from market_data.candles import session_minutes
from market_data.repo.candles import fetch_candles


@dataclass(frozen=True)
class Gap:
    start: datetime  # first missing bar open (UTC)
    end: datetime  # last missing bar open (UTC), inclusive
    minutes: int


@dataclass
class GapReport:
    instrument_id: int
    day: date
    provider: str | None
    expected: int
    present: int
    gaps: list[Gap] = field(default_factory=list)
    duplicates: list[datetime] = field(default_factory=list)

    @property
    def missing(self) -> int:
        return sum(g.minutes for g in self.gaps)

    @property
    def coverage_pct(self) -> float:
        return (
            100.0
            if self.expected == 0
            else round(100.0 * (self.expected - self.missing) / self.expected, 2)
        )

    @property
    def severity(self) -> Severity:
        if self.expected == 0 or (not self.gaps and not self.duplicates):
            return Severity.INFO
        return Severity.ERROR if self.coverage_pct < 95 else Severity.WARN


def find_gaps(candles_1m: Iterable[Candle], calendar: ExchangeCalendar, day: date) -> list[Gap]:
    expected = session_minutes(calendar, day)
    present = {c.ts for c in candles_1m if c.timeframe == Timeframe.M1}
    gaps: list[Gap] = []
    run_start: datetime | None = None
    prev: datetime | None = None
    for ts in expected:
        if ts not in present:
            if run_start is None:
                run_start = ts
            prev = ts
        elif run_start is not None and prev is not None:
            gaps.append(Gap(run_start, prev, int((prev - run_start) / timedelta(minutes=1)) + 1))
            run_start = None
    if run_start is not None and prev is not None:
        gaps.append(Gap(run_start, prev, int((prev - run_start) / timedelta(minutes=1)) + 1))
    return gaps


def find_duplicates(candles: Sequence[Candle]) -> list[datetime]:
    counts = Counter((c.instrument_id, c.timeframe, c.ts, c.provider_id) for c in candles)
    return sorted({k[2] for k, n in counts.items() if n > 1})


async def gap_report(
    session: AsyncSession,
    instrument_id: int,
    day: date,
    provider: str | None,
    calendar: ExchangeCalendar,
    *,
    persist: bool = False,
) -> GapReport:
    bounds = calendar.session_bounds_utc(day)
    expected = session_minutes(calendar, day)
    if bounds is None:
        return GapReport(instrument_id, day, provider, expected=0, present=0)
    candles = await fetch_candles(
        session, instrument_id, Timeframe.M1, bounds[0], bounds[1], provider
    )
    report = GapReport(
        instrument_id=instrument_id,
        day=day,
        provider=provider,
        expected=len(expected),
        present=len({c.ts for c in candles}),
        gaps=find_gaps(candles, calendar, day),
        duplicates=find_duplicates(candles),
    )
    if persist and (report.gaps or report.duplicates):
        if report.gaps:
            session.add(
                DataQualityCheck(
                    instrument_id=instrument_id,
                    timeframe=Timeframe.M1,
                    check_type=QualityCheckType.MISSING_CANDLES,
                    range_from=bounds[0],
                    range_to=bounds[1],
                    severity=report.severity,
                    details={
                        "provider": provider,
                        "missing": report.missing,
                        "expected": report.expected,
                        "gaps": [
                            {
                                "start": g.start.isoformat(),
                                "end": g.end.isoformat(),
                                "minutes": g.minutes,
                            }
                            for g in report.gaps
                        ],
                    },
                )
            )
        if report.duplicates:
            session.add(
                DataQualityCheck(
                    instrument_id=instrument_id,
                    timeframe=Timeframe.M1,
                    check_type=QualityCheckType.DUPLICATES,
                    range_from=bounds[0],
                    range_to=bounds[1],
                    severity=Severity.WARN,
                    details={
                        "provider": provider,
                        "ts": [t.isoformat() for t in report.duplicates],
                    },
                )
            )
        await session.flush()
    return report
