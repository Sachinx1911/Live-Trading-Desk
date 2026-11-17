from datetime import UTC, datetime
from decimal import Decimal

from collector.main import _quote_from_tick
from collector.tracked import parse_symbols
from core.models import DepthLevel, Freshness, Quote, Tick

NOW = datetime(2026, 11, 17, 4, 0, tzinfo=UTC)


def _tick(px: str) -> Tick:
    return Tick(
        instrument_id=22,
        ts=NOW,
        ltp=Decimal(px),
        ltq=10,
        volume=100,
        bids=(DepthLevel(price=Decimal(px) - Decimal("0.05"), quantity=75),),
        asks=(DepthLevel(price=Decimal(px) + Decimal("0.05"), quantity=50),),
        provider_id="fake",
        provider_ts=NOW,
        received_at=NOW,
        is_demo=True,
    )


def test_parse_symbols() -> None:
    assert parse_symbols(" nifty, BANKNIFTY ,,indiavix ") == ["NIFTY", "BANKNIFTY", "INDIAVIX"]


def test_quote_from_tick_carries_provenance_and_depth() -> None:
    q = _quote_from_tick(_tick("100.00"), None)
    assert q.instrument_id == 22 and q.ltp == Decimal("100.00")
    assert q.bid == Decimal("99.95") and q.ask == Decimal("100.05")
    assert q.bid_qty == 75 and q.ask_qty == 50
    assert q.is_demo and q.provider_id == "fake"
    assert q.freshness == Freshness.DEMO


def test_quote_from_tick_tracks_session_high_low() -> None:
    prev = Quote(
        instrument_id=22,
        ts=NOW,
        ltp=Decimal("100"),
        open=Decimal("99"),
        high=Decimal("101"),
        low=Decimal("98"),
        prev_close=Decimal("97"),
        provider_id="fake",
        received_at=NOW,
    )
    q = _quote_from_tick(_tick("102.00"), prev)
    assert q.high == Decimal("102.00") and q.low == Decimal("98") and q.open == Decimal("99")
    assert q.prev_close == Decimal("97")
