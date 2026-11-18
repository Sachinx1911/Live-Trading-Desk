import io
import json
import os
from datetime import UTC, datetime

import polars as pl
import pytest

from core.models import Timeframe
from market_data.imports import ImportMapping, commit_import, parse_upload

CSV = b"""date,open,high,low,close,volume
2026-01-05,100,110,95,105,1000
2026-01-06,105,112,101,108,900
2026-01-06,105,112,101,108,900
2026-01-07,108,109,110,107,500
2026-01-08,bad,109,100,107,500
2026-01-09,107,111,106,110,700
"""


def test_csv_parse_reports_rejections_and_coverage() -> None:
    m = ImportMapping(symbol="NIFTY", ts_column="date", timeframe=Timeframe.D1)
    p = parse_upload("nifty.csv", CSV, m)
    assert p.rows_read == 6 and p.rows_accepted == 3 and p.rows_rejected == 3
    reasons = [r.reason for r in p.rejections]
    assert any("duplicate" in r for r in reasons)
    assert any("OHLC" in r for r in reasons)
    assert any("bad number" in r for r in reasons)
    cov = p.coverage[0]
    assert cov.symbol == "NIFTY" and cov.count == 3
    # 2026-01-05 00:00 IST == 2026-01-04 18:30 UTC
    assert cov.first_ts == datetime(2026, 1, 4, 18, 30, tzinfo=UTC)
    assert all(c.provider_id == "import" and c.instrument_id == 0 for c in p.candles)
    rep = p.report()
    assert rep["rows_accepted"] == 3 and len(rep["content_hash"]) == 64


def test_json_and_parquet_with_symbol_column() -> None:
    rows = [
        {
            "sym": "reliance",
            "ts": "2026-01-05T09:15:00+05:30",
            "o": "100",
            "h": "101",
            "l": "99",
            "c": "100.5",
            "v": "10",
        },
        {
            "sym": "reliance",
            "ts": "2026-01-05T09:16:00+05:30",
            "o": "100.5",
            "h": "102",
            "l": "100",
            "c": "101",
            "v": "12",
        },
        {"sym": "tcs", "ts": "not-a-date", "o": "1", "h": "1", "l": "1", "c": "1", "v": "1"},
    ]
    m = ImportMapping(
        symbol_column="sym",
        ts_column="ts",
        open_column="o",
        high_column="h",
        low_column="l",
        close_column="c",
        volume_column="v",
        timeframe=Timeframe.M1,
    )
    pj = parse_upload("x.json", json.dumps(rows).encode(), m)
    assert pj.rows_accepted == 2 and pj.rejections[0].reason.startswith("bad timestamp")
    assert pj.symbols[0] == "RELIANCE" and pj.candles[0].ts == datetime(
        2026, 1, 5, 3, 45, tzinfo=UTC
    )
    buf = io.BytesIO()
    pl.DataFrame(rows).write_parquet(buf)
    pp = parse_upload("x.parquet", buf.getvalue(), m)
    assert pp.rows_accepted == 2 and pp.rows_rejected == 1
    with pytest.raises(ValueError, match="unsupported"):
        parse_upload("x.exe", b"", m)
    with pytest.raises(ValueError, match="missing columns"):
        parse_upload("x.csv", b"a,b\n1,2\n", ImportMapping(symbol="X"))


def test_epoch_and_custom_format() -> None:
    csv = b"t,open,high,low,close\n1767592800,1,2,0.5,1.5\n05/01/2026 09:15,1,2,0.5,1.5\n"
    p1 = parse_upload(
        "a.csv",
        csv.split(b"\n05/")[0] + b"\n",
        ImportMapping(symbol="X", ts_column="t", volume_column=None),
    )
    assert p1.candles[0].ts == datetime.fromtimestamp(1767592800, tz=UTC)
    p2 = parse_upload(
        "a.csv",
        b"t,open,high,low,close\n05/01/2026 09:15,1,2,0.5,1.5\n",
        ImportMapping(
            symbol="X",
            ts_column="t",
            ts_format="%d/%m/%Y %H:%M",
            volume_column=None,
            timeframe=Timeframe.M1,
        ),
    )
    assert p2.candles[0].ts == datetime(2026, 1, 5, 3, 45, tzinfo=UTC)


@pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set")
async def test_commit_import_writes_job_and_candles() -> None:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from core.db.models import DataImportJob, HistoricalCandle
    from core.settings import Settings
    from market_data.repo.instruments import get_by_symbol

    engine = create_async_engine(Settings().database_url)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        ins = await get_by_symbol(db, "NSE", "NIFTY")
        if ins is None:
            pytest.skip("NIFTY not synced in this database")
        csv = (
            b"date,open,high,low,close,volume\n"
            b"2015-03-02,8000,8050,7950,8020,100\n"
            b"2015-03-03,8020,8100,8000,8090,120\n"
        )
        m = ImportMapping(
            symbol_column=None, symbol="NIFTY", ts_column="date", timeframe=Timeframe.D1
        )
        p = parse_upload("old.csv", csv, m)
        res = await commit_import(db, p, user_id=None, source_uri="old.csv")
        assert res.rows_written == 2 and res.status.value == "succeeded"
        again = await commit_import(db, p, user_id=None, source_uri="old.csv")
        assert again.job_id == res.job_id  # idempotent on the manifest
        job = await db.get(DataImportJob, res.job_id)
        assert job is not None and job.rows_written == 2
        n = (
            (
                await db.execute(
                    select(HistoricalCandle).where(
                        HistoricalCandle.instrument_id == ins.instrument_id,
                        HistoricalCandle.ts == datetime(2015, 3, 1, 18, 30, tzinfo=UTC),
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(n) >= 1
        # unresolved symbol -> failed job, nothing written
        p2 = parse_upload("zz.csv", csv, ImportMapping(symbol="NOPE_XYZ", ts_column="date"))
        res2 = await commit_import(db, p2, user_id=None, source_uri="zz.csv")
        assert res2.status.value == "failed" and res2.unresolved_symbols == ["NOPE_XYZ"]
        await db.rollback()
    await engine.dispose()
