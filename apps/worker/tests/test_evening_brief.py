from datetime import UTC, date, datetime
from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from worker.reports.evening_brief import (
    AccountDay,
    Coverage,
    Facts,
    IndexMove,
    PcrReading,
    build_content,
    render_markdown,
)

DAY = date(2026, 11, 20)


def full_facts() -> Facts:
    return Facts(
        day=DAY,
        is_trading_day=True,
        provider="upstox",
        indices=[
            IndexMove("NIFTY", Decimal("25800.60"), Decimal("25514.30")),
            IndexMove("INDIAVIX", None, Decimal("16.1")),
        ],
        pcr=[
            PcrReading(
                "NIFTY", Decimal("1.7012"), "2026-11-23", datetime(2026, 11, 20, 9, 57, tzinfo=UTC)
            )
        ],
        breadth={
            "advances": 38,
            "declines": 11,
            "unchanged": 1,
            "new_52w_high": 4,
            "new_52w_low": 0,
            "above_ema200_pct": "72.00",
        },
        accounts=[AccountDay(1, "Paper", Decimal("99817.86"), 2, 1, Decimal("-182.14"), 0)],
        alerts_by_severity={"warning": 2},
        rule_blocks=1,
        coverage=[Coverage("NIFTY", 375, 375), Coverage("RELIANCE", 360, 375)],
        next_trading_day=date(2026, 11, 23),
        expiries_next_7d=[{"symbol": "NIFTY", "expiry": "2026-11-23"}],
        headlines=[{"title": "Markets rally", "source": "ET Markets", "url": "https://x"}],
    )


def test_content_is_json_ready_and_computes_moves() -> None:
    c = build_content(full_facts())
    nifty = c["indices"][0]
    assert nifty["change"] == "286.30" and nifty["change_pct"] == "1.12"
    assert c["indices"][1]["change"] is None
    assert c["coverage"][1]["complete"] is False


def test_markdown_states_missing_data_instead_of_numbers() -> None:
    md = render_markdown(build_content(full_facts()))
    assert "NIFTY 25800.60 (+286.30, +1.12%)" in md
    assert "INDIAVIX: no close stored" in md
    assert "RELIANCE: 360/375 bars" in md
    assert "owner-rule blocks: 1" in md
    assert "Markets rally" in md

    empty = render_markdown(build_content(Facts(day=DAY, is_trading_day=False)))
    assert "Market closed today" in empty
    assert "No index candles stored" in empty
    assert "Not computed for today" in empty
    assert "No chain snapshots stored" in empty


@given(
    close=st.decimals(min_value="1", max_value="100000", places=2),
    prev=st.decimals(min_value="1", max_value="100000", places=2),
)
def test_change_pct_sign_matches_change(close: Decimal, prev: Decimal) -> None:
    m = IndexMove("X", close, prev)
    assert m.change == close - prev
    assert m.change_pct is not None
    assert (m.change_pct > 0) == (close > prev) or m.change_pct == 0
