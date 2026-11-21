"""PCR history for simulations (Mark 1, Stage 2): no look-ahead, same rule outcome as paper."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from risk.market_history import PcrHistory, PcrPoint

T0 = datetime(2026, 11, 17, 3, 45, tzinfo=UTC)  # 09:15 IST


def test_context_uses_last_point_at_or_before_now() -> None:
    h = PcrHistory(
        [
            PcrPoint(T0 + timedelta(minutes=3), Decimal("2.1"), "2026-11-25"),
            PcrPoint(T0, Decimal("1.0"), "2026-11-25"),
        ]
    )
    assert h.context_at(T0 - timedelta(seconds=1)).pcr is None  # before the first point
    at_open = h.context_at(T0)
    assert at_open.pcr == Decimal("1.0") and at_open.pcr_ts == T0
    between = h.context_at(T0 + timedelta(minutes=2, seconds=59))
    assert between.pcr == Decimal("1.0")  # the 09:18 point is not visible yet
    later = h.context_at(T0 + timedelta(minutes=10))
    assert later.pcr == Decimal("2.1") and later.pcr_expiry == "2026-11-25"
    assert len(h) == 2 and h.first_ts == T0


@given(
    st.lists(st.integers(min_value=0, max_value=10_000), min_size=0, max_size=50),
    st.integers(min_value=-100, max_value=11_000),
)
def test_never_looks_ahead(offsets: list[int], probe: int) -> None:
    h = PcrHistory(
        PcrPoint(T0 + timedelta(seconds=o), Decimal(o % 7) / 2, "2026-11-25") for o in offsets
    )
    now = T0 + timedelta(seconds=probe)
    ctx = h.context_at(now)
    visible = [T0 + timedelta(seconds=o) for o in offsets if T0 + timedelta(seconds=o) <= now]
    if not visible:
        assert ctx.pcr_ts is None and ctx.pcr is None
    else:
        assert ctx.pcr_ts == max(visible)
        assert ctx.pcr_ts <= now
