"""Importer tests. DB-gated: skipped unless DATABASE_URL is set."""

from __future__ import annotations

import os
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import polars as pl
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from core.db.models import (
    CorporateAction,
    Exchange,
    Instrument,
    InstrumentHistory,
    Segment,
    TradingCalendar,
)
from core.db.models._enums import CorporateActionType, HistoryAttribute, InstrumentType, SessionType
from core.models import Timeframe
from core.settings import Settings
from core.time import utcnow
from providers.nse.importer import (
    bhavcopy_to_candles,
    import_corporate_actions,
    import_fo_lot_sizes,
    import_holidays,
)
from providers.nse.parse import Holiday

pytestmark = pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set")


@pytest.fixture
async def db():
    engine = create_async_engine(Settings().database_url)
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        yield s
        await s.rollback()
    await engine.dispose()


async def _instrument(db, symbol: str, itype: InstrumentType = InstrumentType.EQUITY) -> Instrument:
    ex = (await db.execute(select(Exchange).where(Exchange.code == "NSE"))).scalar_one()
    seg = (await db.execute(select(Segment))).scalars().first()
    uniq = f"{symbol}-T{int(utcnow().timestamp() * 1000) % 10_000_000}"
    inst = Instrument(
        exchange_id=ex.id,
        segment_id=seg.id,
        symbol=uniq,
        name=symbol,
        instrument_type=itype,
        lot_size=1,
        tick_size=Decimal("0.05"),
    )
    db.add(inst)
    await db.flush()
    return inst


async def test_import_holidays_upsert(db) -> None:
    day = date(2099, 1, 26)
    hs = [Holiday(day, "Republic Day", "CM"), Holiday(day, "Republic Day", "FO")]
    c1 = await import_holidays(db, hs)
    assert (c1.inserted, c1.updated, c1.unchanged) == (1, 0, 0)
    c2 = await import_holidays(db, hs)
    assert (c2.inserted, c2.updated, c2.unchanged) == (0, 0, 1)
    c3 = await import_holidays(db, [Holiday(day, "Republic Day (revised)", "CM")])
    assert c3.updated == 1
    ex = (await db.execute(select(Exchange).where(Exchange.code == "NSE"))).scalar_one()
    row = (
        await db.execute(
            select(TradingCalendar).where(
                TradingCalendar.exchange_id == ex.id, TradingCalendar.date == day
            )
        )
    ).scalar_one()
    assert row.session_type == SessionType.HOLIDAY and row.source == "nse"


async def test_import_corporate_actions(db) -> None:
    inst = await _instrument(db, "RELIANCE")
    rows = [
        {
            "symbol": inst.symbol,
            "series": "EQ",
            "subject": "Bonus 1:1",
            "exDate": "28-Oct-2026",
            "recDate": "28-Oct-2026",
        },
        {
            "symbol": inst.symbol,
            "series": "EQ",
            "subject": "Dividend - Rs 5 Per Share",
            "exDate": "10-Aug-2026",
            "recDate": "10-Aug-2026",
        },
        {
            "symbol": inst.symbol,
            "series": "EQ",
            "subject": "Annual General Meeting",
            "exDate": "10-Aug-2026",
        },
        {"symbol": "NOT-TRACKED-XYZ", "subject": "Bonus 1:1", "exDate": "01-Jan-2026"},
        {"symbol": inst.symbol, "subject": "Bonus 1:1", "exDate": "bad date"},
    ]
    c1 = await import_corporate_actions(db, rows)
    assert (c1.inserted, c1.skipped) == (2, 3)
    c2 = await import_corporate_actions(db, rows)
    assert (c2.inserted, c2.unchanged) == (0, 2)
    cas = (
        (
            await db.execute(
                select(CorporateAction)
                .where(CorporateAction.instrument_id == inst.id)
                .order_by(CorporateAction.ex_date)
            )
        )
        .scalars()
        .all()
    )
    assert [c.action_type for c in cas] == [CorporateActionType.DIVIDEND, CorporateActionType.BONUS]
    assert cas[0].amount == Decimal("5")
    bonus = cas[1]
    assert (bonus.ratio_from, bonus.ratio_to) == (1, 1)
    assert bonus.adjustment_factor == Decimal("0.5")
    assert bonus.raw["subject"] == "Bonus 1:1"


async def test_import_fo_lot_sizes_records_changes_only(db) -> None:
    inst = await _instrument(db, "NIFTY", InstrumentType.INDEX)
    other = await _instrument(db, "RELIANCE")

    def fo(lot_nifty: int, lot_rel: int) -> pl.DataFrame:
        return pl.DataFrame(
            {
                "symbol": [inst.symbol, inst.symbol, other.symbol, "UNKNOWN-SYM"],
                "instrument_type": ["FUTIDX", "FUTIDX", "FUTSTK", "FUTSTK"],
                "expiry": [
                    date(2026, 12, 30),
                    date(2026, 11, 25),
                    date(2026, 11, 25),
                    date(2026, 11, 25),
                ],
                "lot_size": [lot_nifty, lot_nifty, lot_rel, 1],
            }
        )

    c1 = await import_fo_lot_sizes(db, date(2026, 11, 14), fo(75, 500))
    assert (c1.inserted, c1.skipped) == (2, 1)
    c2 = await import_fo_lot_sizes(db, date(2026, 11, 17), fo(75, 500))
    assert (c2.inserted, c2.unchanged) == (0, 2)
    c3 = await import_fo_lot_sizes(db, date(2026, 11, 18), fo(65, 500))
    assert c3.inserted == 1
    # An older file must not rewrite newer history.
    c4 = await import_fo_lot_sizes(db, date(2026, 11, 10), fo(50, 500))
    assert c4.skipped >= 1 and c4.inserted == 0
    hist = (
        (
            await db.execute(
                select(InstrumentHistory)
                .where(
                    InstrumentHistory.instrument_id == inst.id,
                    InstrumentHistory.attribute == HistoryAttribute.LOT_SIZE,
                )
                .order_by(InstrumentHistory.effective_from)
            )
        )
        .scalars()
        .all()
    )
    assert [(h.old_value, h.new_value, h.effective_from) for h in hist] == [
        (None, "75", date(2026, 11, 14)),
        ("75", "65", date(2026, 11, 18)),
    ]


def test_bhavcopy_to_candles() -> None:
    df = pl.DataFrame(
        {
            "symbol": ["RELIANCE", "TCS", "JUNK"],
            "isin": ["INE002A01018", "INE467B01029", None],
            "series": ["EQ", "EQ", "SM"],
            "date": [date(2026, 11, 14)] * 3,
            "open": [Decimal("1450"), Decimal("3520"), Decimal("1")],
            "high": [Decimal("1462.5"), Decimal("3555"), Decimal("1")],
            "low": [Decimal("1441.1"), Decimal("3501"), Decimal("1")],
            "close": [Decimal("1465"), Decimal("3540.25"), Decimal("1")],  # RELIANCE close > high
            "last": [None, None, None],
            "prev_close": [None, None, None],
            "volume": [8123456, 1523456, 0],
            "turnover": [None, None, None],
            "trades": [201345, 98765, 0],
        }
    )
    candles = bhavcopy_to_candles(df, {"RELIANCE": 11, "JUNK": 99})
    assert len(candles) == 1
    c = candles[0]
    assert c.instrument_id == 11 and c.timeframe == Timeframe.D1 and c.provider_id == "import"
    assert c.ts == datetime(2026, 11, 14, 9, 15, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert c.high == Decimal("1465") and c.close == Decimal("1465")  # clamped, still valid OHLC
    assert c.volume == 8123456 and c.trade_count == 201345 and not c.is_demo
