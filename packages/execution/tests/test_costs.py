"""Hand-computed contract notes against the static 2025-10 schedule."""

from datetime import date
from decimal import Decimal

from core.models import OrderSide, ProductType, Segment
from execution.costs import CostModel, RowSchedule, StaticCostSchedule

ON = date(2026, 11, 17)
cm = CostModel(StaticCostSchedule())


def test_equity_intraday_buy_then_sell() -> None:
    # Buy 100 @ 1000 = 1,00,000: brokerage 20, STT nil (buy), NSE 0.00297% = 2.97,
    # SEBI 0.0001% = 0.10, stamp 0.003% = 3.00, GST 18% of (20 + 2.97 + 0.10) = 4.15
    b = cm.compute(
        segment=Segment.EQUITY,
        product=ProductType.INTRADAY,
        side=OrderSide.BUY,
        quantity=100,
        price=Decimal(1000),
        on=ON,
    )
    assert (b.brokerage, b.stt, b.exchange, b.sebi, b.stamp, b.gst) == (
        Decimal("20.00"),
        Decimal("0.00"),
        Decimal("2.97"),
        Decimal("0.10"),
        Decimal("3.00"),
        Decimal("4.15"),
    )
    assert b.total == Decimal("30.22")
    # Sell 100 @ 1010 = 1,01,000: STT 0.025% = 25.25, NSE 3.00, SEBI 0.10, stamp nil,
    # GST 18% of (20 + 2.9997 + 0.101) = 4.16
    s = cm.compute(
        segment=Segment.EQUITY,
        product=ProductType.INTRADAY,
        side=OrderSide.SELL,
        quantity=100,
        price=Decimal(1010),
        on=ON,
    )
    assert (s.stt, s.exchange, s.stamp, s.gst) == (
        Decimal("25.25"),
        Decimal("3.00"),
        Decimal("0.00"),
        Decimal("4.16"),
    )
    assert s.total == Decimal("52.51")


def test_nifty_futures_carry() -> None:
    # Buy 75 @ 24000 = 18,00,000: NSE 0.00173% = 31.14, SEBI 1.80, stamp 0.002% = 36.00,
    # GST 18% of (20 + 31.14 + 1.80) = 9.53 -> 98.47
    b = cm.compute(
        segment=Segment.FUTURES,
        product=ProductType.CARRY,
        side=OrderSide.BUY,
        quantity=75,
        price=Decimal(24000),
        lots=1,
        on=ON,
    )
    assert b.total == Decimal("98.47") and b.stt == 0
    # Sell 75 @ 24100 = 18,07,500: STT 0.02% = 361.50, NSE 31.27, SEBI 1.81, stamp nil,
    # GST 18% of (20 + 31.26975 + 1.8075) = 9.55 -> 424.13
    s = cm.compute(
        segment=Segment.FUTURES,
        product=ProductType.CARRY,
        side=OrderSide.SELL,
        quantity=75,
        price=Decimal(24100),
        lots=1,
        on=ON,
    )
    assert (s.stt, s.exchange, s.sebi, s.gst) == (
        Decimal("361.50"),
        Decimal("31.27"),
        Decimal("1.81"),
        Decimal("9.55"),
    )
    assert s.total == Decimal("424.13")


def test_nifty_option_buy_then_sell() -> None:
    # Buy 75 @ 100 premium = 7,500: NSE 0.03503% = 2.63, SEBI 0.01, stamp 0.003% = 0.23,
    # GST 18% of (20 + 2.62725 + 0.0075) = 4.07 -> 26.94
    b = cm.compute(
        segment=Segment.OPTIONS,
        product=ProductType.INTRADAY,
        side=OrderSide.BUY,
        quantity=75,
        price=Decimal(100),
        on=ON,
    )
    assert b.total == Decimal("26.94")
    # Sell 75 @ 120 = 9,000: STT 0.1% of premium = 9.00, NSE 3.15, SEBI 0.01, GST 4.17 -> 36.33
    s = cm.compute(
        segment=Segment.OPTIONS,
        product=ProductType.INTRADAY,
        side=OrderSide.SELL,
        quantity=75,
        price=Decimal(120),
        on=ON,
    )
    assert (s.stt, s.exchange, s.gst) == (Decimal("9.00"), Decimal("3.15"), Decimal("4.17"))
    assert s.total == Decimal("36.33")


class _Row:
    def __init__(self, **kw: object) -> None:
        self.__dict__.update(kw)


def test_row_schedule_matches_static_for_intraday_sell() -> None:
    rows = [
        _Row(
            product="intraday",
            charge_type="brokerage",
            side="both",
            rate_type="flat_per_order",
            rate="20",
            cap=None,
            effective_from=date(2025, 10, 1),
            effective_to=None,
        ),
        _Row(
            product="intraday",
            charge_type="stt",
            side="sell",
            rate_type="percent",
            rate="0.00025",
            cap=None,
            effective_from=date(2025, 10, 1),
            effective_to=None,
        ),
        _Row(
            product="intraday",
            charge_type="exchange_txn",
            side="both",
            rate_type="percent",
            rate="0.0000297",
            cap=None,
            effective_from=date(2025, 10, 1),
            effective_to=None,
        ),
        _Row(
            product="intraday",
            charge_type="sebi",
            side="both",
            rate_type="percent",
            rate="0.000001",
            cap=None,
            effective_from=date(2025, 10, 1),
            effective_to=None,
        ),
        _Row(
            product="intraday",
            charge_type="stamp_duty",
            side="buy",
            rate_type="percent",
            rate="0.00003",
            cap=None,
            effective_from=date(2025, 10, 1),
            effective_to=None,
        ),
    ]
    db = CostModel(RowSchedule(rows))
    a = db.compute(
        segment=Segment.EQUITY,
        product=ProductType.INTRADAY,
        side=OrderSide.SELL,
        quantity=100,
        price=Decimal(1010),
        on=ON,
    )
    assert a.total == Decimal("52.51")
    # before effective_from nothing applies
    z = db.compute(
        segment=Segment.EQUITY,
        product=ProductType.INTRADAY,
        side=OrderSide.SELL,
        quantity=100,
        price=Decimal(1010),
        on=date(2020, 1, 1),
    )
    assert z.total == 0
