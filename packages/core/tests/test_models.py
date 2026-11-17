from datetime import UTC, datetime
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from core.models import Candle, OrderStatus, Quote, Timeframe
from core.models.enums import ORDER_TRANSITIONS, can_transition

NOW = datetime(2026, 11, 17, 9, 15, tzinfo=UTC)


def test_candle_rejects_inconsistent_ohlc() -> None:
    with pytest.raises(ValueError):
        Candle(
            instrument_id=1,
            timeframe=Timeframe.M1,
            ts=NOW,
            open=Decimal(10),
            high=Decimal(9),
            low=Decimal(8),
            close=Decimal(9),
            provider_id="fake",
            received_at=NOW,
        )


def test_candle_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError):
        Candle(
            instrument_id=1,
            timeframe=Timeframe.M1,
            ts=datetime(2026, 1, 1),
            open=Decimal(1),
            high=Decimal(1),
            low=Decimal(1),
            close=Decimal(1),
            provider_id="fake",
            received_at=NOW,
        )


def test_quote_change_pct() -> None:
    q = Quote(
        instrument_id=1,
        ts=NOW,
        ltp=Decimal(110),
        prev_close=Decimal(100),
        provider_id="fake",
        received_at=NOW,
    )
    assert q.change == Decimal(10)
    assert q.change_pct == Decimal(10)


def test_terminal_states_have_no_transitions() -> None:
    for s in OrderStatus:
        if s.is_terminal:
            assert ORDER_TRANSITIONS[s] == frozenset()


@given(st.sampled_from(list(OrderStatus)), st.sampled_from(list(OrderStatus)))
def test_can_transition_matches_table(a: OrderStatus, b: OrderStatus) -> None:
    assert can_transition(a, b) == (b in ORDER_TRANSITIONS[a])


def test_rejected_never_reaches_submitted() -> None:
    assert not can_transition(OrderStatus.REJECTED, OrderStatus.SUBMITTED)


def test_timeframe_durations() -> None:
    assert Timeframe.M5.duration is not None and Timeframe.M5.duration.total_seconds() == 300
    assert Timeframe.W1.duration is None
    assert Timeframe.M15.is_intraday and not Timeframe.D1.is_intraday
