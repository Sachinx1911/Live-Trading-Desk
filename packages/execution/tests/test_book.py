from datetime import timedelta
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from core.models import Fill, OrderSide, TradingMode
from execution.orders import Order
from execution.simulator import PositionBook
from tests.conftest import T0, make_intent


def _fill(book: PositionBook, side: OrderSide, qty: int, px: str, cost: str = "0", i: int = 0):  # type: ignore[no-untyped-def]
    o = Order(intent=make_intent(side=side, qty=qty))
    f = Fill(
        order_id=o.order_id,
        ts=T0 + timedelta(seconds=i),
        quantity=qty,
        price=Decimal(px),
        costs=Decimal(cost),
    )
    return book.apply(o, f)


def test_round_trip_long_with_costs() -> None:
    book = PositionBook(account_id=1, mode=TradingMode.PAPER, initial_cash=Decimal(100000))
    assert _fill(book, OrderSide.BUY, 10, "100", "1") is None
    assert book.position(22).quantity == 10 and book.cash == Decimal(100000 - 1000 - 1)
    book.mark(22, Decimal("105"))
    assert book.unrealized == Decimal(50) and book.realized == Decimal(-1)
    closed = _fill(book, OrderSide.SELL, 10, "110", "1", i=60)
    assert closed is not None
    assert (closed.gross_pnl, closed.costs, closed.net_pnl) == (
        Decimal(100),
        Decimal(2),
        Decimal(98),
    )
    assert closed.entry_price == Decimal(100) and closed.exit_price == Decimal(110)
    assert closed.duration_s == 60 and closed.side == OrderSide.BUY
    assert (
        book.position(22).is_flat
        and book.realized == Decimal(98)
        and book.equity == Decimal(100098)
    )


def test_short_round_trip_and_flip() -> None:
    book = PositionBook(account_id=1, mode=TradingMode.PAPER, initial_cash=Decimal(0))
    _fill(book, OrderSide.SELL, 5, "100")
    assert book.position(22).quantity == -5
    closed = _fill(book, OrderSide.BUY, 8, "90", i=1)  # closes short +50, opens long 3 @ 90
    assert closed is not None and closed.net_pnl == Decimal(50) and closed.side == OrderSide.SELL
    p = book.position(22)
    assert p.quantity == 3 and p.avg_price == Decimal(90)


@settings(max_examples=200, deadline=None)
@given(
    st.lists(
        st.tuples(
            st.sampled_from([OrderSide.BUY, OrderSide.SELL]),
            st.integers(1, 50),
            st.integers(9000, 11000),
            st.integers(0, 300),
        ),
        min_size=1,
        max_size=25,
    )
)
def test_accounting_identity_holds(fills: list[tuple[OrderSide, int, int, int]]) -> None:
    book = PositionBook(account_id=1, mode=TradingMode.PAPER, initial_cash=Decimal(500000))
    for i, (side, qty, px100, cost100) in enumerate(fills):
        _fill(book, side, qty, str(Decimal(px100) / 100), str(Decimal(cost100) / 100), i)
        # identity: cash + market value - initial == realized + unrealized
        # (average prices are repeating decimals; equality holds to far below a paisa)
        lhs = book.cash + book.market_value - book.initial_cash
        assert abs(lhs - (book.realized + book.unrealized)) < Decimal("0.000001")


@settings(max_examples=200, deadline=None)
@given(st.lists(st.tuples(st.booleans(), st.integers(1, 20)), min_size=1, max_size=30))
def test_long_only_never_negative(ops: list[tuple[bool, int]]) -> None:
    book = PositionBook(account_id=1, mode=TradingMode.PAPER, initial_cash=Decimal(10**7))
    for i, (buy, qty) in enumerate(ops):
        if buy:
            _fill(book, OrderSide.BUY, qty, "100", i=i)
        else:
            have = book.position(22).quantity
            if have > 0:
                _fill(book, OrderSide.SELL, min(qty, have), "101", i=i)
        assert book.position(22).quantity >= 0
