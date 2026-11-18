from datetime import UTC, datetime, timedelta
from decimal import Decimal

from core.calendar import nse_calendar
from core.models import Candle, Timeframe
from trader.bars import BarAggregator

CAL = nse_calendar()
OPEN = datetime(2026, 11, 18, 3, 45, tzinfo=UTC)  # 09:15 IST


def _c(i: int, px: float) -> Candle:
    ts = OPEN + timedelta(minutes=i)
    return Candle(
        instrument_id=30,
        timeframe=Timeframe.M1,
        ts=ts,
        open=Decimal(px),
        high=Decimal(px + 2),
        low=Decimal(px - 1),
        close=Decimal(px + 1),
        volume=10,
        provider_id="fake",
        received_at=ts,
    )


def test_five_minute_buckets_align_to_session_open() -> None:
    agg = BarAggregator(Timeframe.M5, CAL)
    out = [b for i in range(11) if (b := agg.on_1m(_c(i, 100 + i))) is not None]
    assert [b.ts for b in out] == [OPEN, OPEN + timedelta(minutes=5)]
    first = out[0]
    assert first.open == Decimal(100) and first.close == Decimal(105)  # close of minute 4 (+1)
    assert first.high == Decimal(106) and first.low == Decimal(99) and first.volume == 50
    assert first.derived_from == Timeframe.M1 and first.timeframe == Timeframe.M5


def test_one_minute_passthrough_and_flush() -> None:
    agg = BarAggregator(Timeframe.M1, CAL)
    assert agg.on_1m(_c(0, 100)) is not None
    agg5 = BarAggregator(Timeframe.M5, CAL)
    assert agg5.on_1m(_c(0, 100)) is None
    assert agg5.flush() is not None and agg5.flush() is None


def test_maybe_close_after_bucket_end_plus_grace() -> None:
    agg = BarAggregator(Timeframe.M5, CAL)
    agg.on_1m(_c(0, 100))
    assert agg.maybe_close(OPEN + timedelta(minutes=5, seconds=5)) is None
    assert agg.maybe_close(OPEN + timedelta(minutes=5, seconds=25)) is not None
