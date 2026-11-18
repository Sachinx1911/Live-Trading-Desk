import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from core.models import AssetClass, OptionType, Segment, Timeframe
from providers.upstox.mapping import (
    chunk_ranges,
    expiry_from_ms,
    map_candles,
    map_instruments,
    map_option_chain,
    map_quotes,
)

FIX = Path(__file__).parent / "fixtures" / "upstox"
NOW = datetime(2025, 11, 17, 4, 0, tzinfo=UTC)


def _load(name: str):  # type: ignore[no-untyped-def]
    return json.loads((FIX / name).read_text())


def test_map_instruments_covers_index_equity_fno_and_skips_etf() -> None:
    insts, keys = map_instruments(_load("instruments_nse.json"))
    by_symbol = {i.symbol: i for i in insts}
    assert set(by_symbol) == {
        "NIFTY",
        "RELIANCE",
        "TCS",
        "NIFTYFUT27NOV25",
        "NIFTY26000CE20NOV25",
        "NIFTY26000PE20NOV25",
    }
    nifty = by_symbol["NIFTY"]
    assert nifty.segment is Segment.INDEX and nifty.asset_class is AssetClass.INDEX
    assert keys[nifty.instrument_id] == "NSE_INDEX|Nifty 50"
    rel = by_symbol["RELIANCE"]
    assert rel.isin == "INE002A01018" and rel.tick_size == Decimal("5.0")
    fut = by_symbol["NIFTYFUT27NOV25"]
    assert fut.segment is Segment.FUTURES and fut.lot_size == 75
    assert fut.expiry == date(2025, 11, 28)
    ce = by_symbol["NIFTY26000CE20NOV25"]
    assert ce.option_type is OptionType.CE and ce.strike == Decimal("26000.0")
    assert ce.underlying_symbol == "NIFTY" and ce.expiry == date(2025, 11, 19)
    assert all(i.instrument_id >= 1_000_000 for i in insts)


def test_expiry_from_ms_uses_ist_date() -> None:
    # 1763576999000 = 2025-11-19 23:59:59 IST
    assert expiry_from_ms(1763576999000) == date(2025, 11, 19)
    assert expiry_from_ms(None) is None


def test_map_candles_sorted_ascending_utc() -> None:
    candles = map_candles(_load("historical_5m.json"), 7, Timeframe.M5, NOW)
    assert [c.ts for c in candles] == sorted(c.ts for c in candles)
    first = candles[0]
    assert first.ts == datetime(2025, 11, 14, 3, 45, tzinfo=UTC)  # 09:15 IST
    assert first.open == Decimal("25880.0") and first.provider_id == "upstox"
    assert first.is_demo is False and first.instrument_id == 7


def test_chunk_ranges() -> None:
    chunks = chunk_ranges(date(2025, 1, 1), date(2025, 3, 15), 30)
    assert chunks[0] == (date(2025, 1, 1), date(2025, 1, 30))
    assert chunks[-1][1] == date(2025, 3, 15)
    assert all((b - a).days < 30 for a, b in chunks)
    assert chunk_ranges(date(2025, 1, 2), date(2025, 1, 1), 30) == []


def test_map_quotes_depth_and_prev_close() -> None:
    ids = {"NSE_EQ|INE002A01018": 11, "NSE_INDEX|Nifty 50": 1}
    quotes = {q.instrument_id: q for q in map_quotes(_load("quotes.json"), ids, NOW)}
    rel = quotes[11]
    assert (
        rel.ltp == Decimal("1490.2")
        and rel.bid == Decimal("1490.1")
        and rel.ask == Decimal("1490.3")
    )
    assert rel.bid_qty == 120 and rel.volume == 5432100
    assert rel.prev_close == Decimal("1482.3")
    assert rel.ts == datetime.fromtimestamp(1763114398, tz=UTC)
    nifty = quotes[1]
    assert nifty.bid is None and nifty.change == Decimal("45.0")


def test_map_option_chain_rows_and_oi_change() -> None:
    ids = {"NSE_FO|40001": 21, "NSE_FO|40002": 22}
    snap = map_option_chain(
        _load("option_chain.json"), 1, datetime(2025, 11, 20, tzinfo=UTC), ids, NOW
    )
    assert snap.underlying_price == Decimal("25955.0") and len(snap.rows) == 2
    ce = next(r for r in snap.rows if r.option_type is OptionType.CE)
    assert ce.instrument_id == 21 and ce.oi == 4567800 and ce.oi_change == 467800
    assert ce.iv == Decimal("13.2") and ce.delta == Decimal("0.47")
    pe = next(r for r in snap.rows if r.option_type is OptionType.PE)
    assert pe.oi_change == -210000


def test_daily_candles_use_session_open_not_midnight() -> None:
    from datetime import UTC, datetime

    body = {
        "status": "success",
        "data": {"candles": [["2026-11-16T00:00:00+05:30", 1, 2, 0.5, 1.5, 10, 0]]},
    }
    (c,) = map_candles(body, 7, Timeframe.D1, NOW)
    # 09:15 IST on 16 Nov == 03:45 UTC on 16 Nov; midnight IST would have been 15 Nov UTC
    assert c.ts == datetime(2026, 11, 16, 3, 45, tzinfo=UTC)
    assert c.ts.date().isoformat() == "2026-11-16"


def test_inconsistent_ohlc_is_widened_not_dropped() -> None:
    body = {
        "status": "success",
        "data": {"candles": [["2026-11-16T00:00:00+05:30", 12.5, 12.0, 11.0, 10.5, 0, 0]]},
    }
    (c,) = map_candles(body, 7, Timeframe.D1, NOW)
    assert c.high == Decimal("12.5") and c.low == Decimal("10.5")
