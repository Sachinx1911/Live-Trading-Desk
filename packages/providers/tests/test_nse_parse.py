# ruff: noqa: E501 - fixture CSV rows are intentionally long
"""Parser tests: holidays JSON, CM and FO bhavcopy zips, corporate action subjects."""

from __future__ import annotations

import io
import zipfile
from datetime import date
from decimal import Decimal

import pytest

from providers.nse.parse import (
    adjustment_factor,
    parse_cm_bhavcopy,
    parse_corporate_action_subject,
    parse_fo_bhavcopy,
    parse_holidays,
)

HOLIDAYS = {
    "CM": [
        {"tradingDate": "26-Jan-2026", "weekDay": "Monday", "description": "Republic Day"},
        {"tradingDate": "26-Jan-2026", "weekDay": "Monday", "description": "Republic Day"},
        {"tradingDate": "garbage", "description": "bad"},
        {"tradingDate": "15-Aug-2026", "description": "Independence Day"},
        "not a dict",
    ],
    "FO": [{"tradingDate": "26-Jan-2026", "description": "Republic Day"}],
    "CD": [{"tradingDate": "01-May-2026", "description": "ignored segment"}],
}


def _zip(name: str, csv: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(name, csv)
    return buf.getvalue()


CM_CSV = """TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,XpryDt,FininstrmActlXpryDt,StrkPric,OptnTp,FinInstrmNm,OpnPric,HghPric,LwPric,ClsPric,LastPric,PrvsClsgPric,UndrlygPric,SttlmPric,OpnIntrst,ChngInOpnIntrst,TtlTradgVol,TtlTrfVal,TtlNbOfTxsExctd,SsnId,NewBrdLotQty,Rmks,Rsvd1,Rsvd2,Rsvd3,Rsvd4
2026-11-14,2026-11-14,CM,NSE,STK,2885,INE002A01018,RELIANCE,EQ,,,,,RELIANCE INDUSTRIES LTD,1450.00,1462.50,1441.10,1455.30,1455.00,1448.20,,,,,8123456,118234567890.50,201345,F1,,,,,,
2026-11-14,2026-11-14,CM,NSE,STK,11536,INE467B01029,TCS,EQ,,,,,TATA CONSULTANCY SERV LT,3520.00,3555.00,3501.00,3540.25,3540.00,3518.70,,,,,1523456,53912345678.00,98765,F1,,,,,,
2026-11-14,2026-11-14,CM,NSE,STK,1333,INE040A01034,HDFCBANK,EQ,,,,,HDFC BANK LTD,"1,700.00",1712.00,1690.00,1705.10,1705.00,1698.00,,,,,5234567,89012345678.00,150000,F1,,,,,,
2026-11-14,2026-11-14,CM,NSE,STK,999,INE999Z01010,JUNKCO,BE,,,,,JUNK CO,-,NA,,,,,,,,,0,0,0,F1,,,,,,
2026-11-14,2026-11-14,CM,NSE,STK,3045,INE062A01020,SBIN,EQ,,,,,STATE BANK OF INDIA,800.00,812.00,798.50,810.00,810.05,799.00,,,,,9000000,72500000000.00,220000,F1,,,,,,
"""

FO_CSV = """TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,XpryDt,FininstrmActlXpryDt,StrkPric,OptnTp,FinInstrmNm,OpnPric,HghPric,LwPric,ClsPric,LastPric,PrvsClsgPric,UndrlygPric,SttlmPric,OpnIntrst,ChngInOpnIntrst,TtlTradgVol,TtlTrfVal,TtlNbOfTxsExctd,SsnId,NewBrdLotQty,Rmks,Rsvd1,Rsvd2,Rsvd3,Rsvd4
2026-11-14,2026-11-14,FO,NSE,FUTIDX,35000,,NIFTY,,2026-11-25,2026-11-25,,,NIFTY26NOVFUT,25500.00,25600.00,25450.00,25550.00,25550.00,25480.00,25530.00,25550.00,1234567,12345,345678,1.0,45678,F1,75,,,,,
2026-11-14,2026-11-14,FO,NSE,FUTIDX,35001,,NIFTY,,2026-12-30,2026-12-30,,,NIFTY26DECFUT,25600.00,25700.00,25550.00,25650.00,25650.00,25580.00,25530.00,25650.00,234567,2345,45678,1.0,5678,F1,75,,,,,
2026-11-14,2026-11-14,FO,NSE,OPTIDX,35002,,NIFTY,,2026-11-18,2026-11-18,25500.00,CE,NIFTY26N1825500CE,120.00,150.00,100.00,130.00,130.00,110.00,25530.00,130.00,9876543,98765,7654321,1.0,654321,F1,75,,,,,
2026-11-14,2026-11-14,FO,NSE,OPTIDX,35003,,NIFTY,,2026-11-18,2026-11-18,25500.00,PE,NIFTY26N1825500PE,90.00,110.00,80.00,95.00,95.00,100.00,25530.00,95.00,8765432,-8765,6543210,1.0,543210,F1,75,,,,,
2026-11-14,2026-11-14,FO,NSE,FUTSTK,36000,,RELIANCE,,2026-11-25,2026-11-25,,,RELIANCE26NOVFUT,1455.00,1465.00,1445.00,1460.00,1460.00,1452.00,1455.30,1460.00,345678,3456,56789,1.0,6789,F1,500,,,,,
2026-11-14,2026-11-14,FO,NSE,IDX,0,,NIFTY,,,,,,NIFTY SPOT,25500.00,25600.00,25450.00,25530.00,,,,,,,,,,F1,,,,,,
"""


def test_parse_holidays_dedupes_and_filters_segments() -> None:
    hs = parse_holidays(HOLIDAYS)
    assert [(h.day, h.segment) for h in hs] == [
        (date(2026, 1, 26), "CM"),
        (date(2026, 1, 26), "FO"),
        (date(2026, 8, 15), "CM"),
    ]
    assert hs[0].description == "Republic Day"
    assert parse_holidays({"CM": "nope"}) == []


def test_parse_cm_bhavcopy() -> None:
    df = parse_cm_bhavcopy(_zip("BhavCopy_NSE_CM_0_0_0_20261114_F_0000.csv", CM_CSV))
    assert df.height == 4  # JUNKCO dropped: unparsable prices
    assert df.columns[:4] == ["symbol", "isin", "series", "date"]
    rel = df.filter(df["symbol"] == "RELIANCE").row(0, named=True)
    assert rel["isin"] == "INE002A01018" and rel["series"] == "EQ"
    assert rel["date"] == date(2026, 11, 14)
    assert Decimal(str(rel["close"])) == Decimal("1455.3000")
    assert rel["volume"] == 8123456 and rel["trades"] == 201345
    hdfc = df.filter(df["symbol"] == "HDFCBANK").row(0, named=True)
    assert Decimal(str(hdfc["open"])) == Decimal("1700.0000")  # thousands separator handled


def test_parse_cm_bhavcopy_accepts_plain_csv_and_rejects_garbage() -> None:
    assert parse_cm_bhavcopy(CM_CSV.encode()).height == 4
    with pytest.raises(ValueError):
        parse_cm_bhavcopy(_zip("x.csv", "a,b\n1,2\n"))


def test_parse_fo_bhavcopy() -> None:
    df = parse_fo_bhavcopy(_zip("fo.csv", FO_CSV))
    assert df.height == 5  # IDX row dropped
    nifty_fut = df.filter((df["symbol"] == "NIFTY") & (df["instrument_type"] == "FUTIDX")).sort(
        "expiry"
    )
    assert nifty_fut["expiry"].to_list() == [date(2026, 11, 25), date(2026, 12, 30)]
    assert nifty_fut["lot_size"].to_list() == [75, 75]
    assert nifty_fut["strike"].to_list() == [None, None]
    pe = df.filter(df["option_type"] == "PE").row(0, named=True)
    assert Decimal(str(pe["strike"])) == Decimal("25500.00") and pe["oi_change"] == -8765
    assert df.filter(df["symbol"] == "RELIANCE")["lot_size"].item() == 500


@pytest.mark.parametrize(
    ("subject", "kind", "num", "den", "amount"),
    [
        ("Bonus 1:1", "bonus", 1, 1, None),
        ("Bonus 3:2", "bonus", 3, 2, None),
        ("Face Value Split From Rs.10/- To Rs.2/-", "split", 5, 1, None),
        (
            "Face Value Split (Sub-Division) - From Rs 2/- Per Share To Re 1/- Per Share",
            "split",
            2,
            1,
            None,
        ),
        ("Dividend - Rs 5 Per Share", "dividend", None, None, Decimal("5")),
        ("Interim Dividend - Rs 12.50 Per Share", "dividend", None, None, Decimal("12.50")),
        ("Final Dividend - Re 0.75 Per Share", "dividend", None, None, Decimal("0.75")),
        ("Rights 1:4 @ Premium Rs 90/- Per Share", "rights", 1, 4, None),
        ("Annual General Meeting", "other", None, None, None),
        ("Bonus issue (ratio to be announced)", "other", None, None, None),
        ("", "other", None, None, None),
    ],
)
def test_parse_corporate_action_subject(subject, kind, num, den, amount) -> None:
    spec = parse_corporate_action_subject(subject)
    assert spec.kind == kind
    assert spec.ratio_num == num and spec.ratio_den == den
    assert spec.amount == amount
    assert spec.raw == subject.strip()


def test_adjustment_factor() -> None:
    assert adjustment_factor(parse_corporate_action_subject("Bonus 1:1")) == Decimal("0.5")
    assert adjustment_factor(
        parse_corporate_action_subject("Face Value Split From Rs.10/- To Rs.2/-")
    ) == Decimal("0.2")
    assert adjustment_factor(parse_corporate_action_subject("Dividend - Rs 5 Per Share")) is None
