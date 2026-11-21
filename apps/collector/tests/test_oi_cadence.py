from datetime import UTC, datetime, timedelta

from collector.oi_cadence import summarise

T0 = datetime(2026, 11, 23, 4, 0, tzinfo=UTC)


def test_summarise_gaps() -> None:
    times = [T0, T0 + timedelta(seconds=180), T0 + timedelta(seconds=375)]
    assert summarise(times) == {"changes": 3, "min_s": 180.0, "median_s": 187.5, "max_s": 195.0}


def test_summarise_needs_two_changes() -> None:
    assert summarise([T0])["median_s"] is None
    assert summarise([])["changes"] == 0
