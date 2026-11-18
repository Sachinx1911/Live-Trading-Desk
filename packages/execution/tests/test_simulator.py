from datetime import timedelta
from decimal import Decimal

from core.calendar import nse_calendar
from core.models import OrderSide, OrderStatus, OrderType
from execution.simulator import ExecutionSimulator, MarketState, SpreadAwareSlippage
from tests.conftest import T0, make_intent, make_quote


def _sim(**kw: object) -> ExecutionSimulator:
    return ExecutionSimulator(seed=7, calendar=nse_calendar(), **kw)  # type: ignore[arg-type]


def test_market_order_never_fills_on_creating_event_then_fills_at_ask() -> None:
    sim = _sim()
    q0 = make_quote("100", bid="99.95", ask="100.05", bid_qty=500, ask_qty=500)
    o = sim.submit(make_intent(qty=100), MarketState(ts=T0, quote=q0))
    assert o.status == OrderStatus.OPEN
    assert sim.on_market(22, MarketState(ts=T0, quote=q0)) == []
    t1 = T0 + timedelta(seconds=1)
    q1 = make_quote("100.10", bid="100.05", ask="100.15", bid_qty=500, ask_qty=500, ts=t1)
    fills = sim.on_market(22, MarketState(ts=t1, quote=q1))
    assert len(fills) == 1 and fills[0].price == Decimal("100.15") and fills[0].quantity == 100
    assert fills[0].costs > 0 and o.status == OrderStatus.FILLED


def test_partial_fills_bounded_then_remainder() -> None:
    sim = _sim(max_partial_events=2)
    sim.submit(make_intent(qty=100), MarketState(ts=T0, quote=make_quote("100")))
    qtys = []
    for i in range(1, 5):
        t = T0 + timedelta(seconds=i)
        q = make_quote("100", bid="99.95", ask="100.05", bid_qty=30, ask_qty=30, ts=t)
        for f in sim.on_market(22, MarketState(ts=t, quote=q)):
            qtys.append((f.quantity, f.is_partial))
    assert qtys == [(30, True), (30, True), (40, False)]


def test_limit_fills_only_when_crossed_with_improvement() -> None:
    sim = _sim()
    sim.submit(
        make_intent(qty=10, order_type=OrderType.LIMIT, limit=Decimal("99")),
        MarketState(ts=T0, quote=make_quote("100")),
    )
    t1 = T0 + timedelta(seconds=1)
    assert (
        sim.on_market(22, MarketState(ts=t1, quote=make_quote("99.5", ask="99.55", bid="99.45")))
        == []
    )
    t2 = T0 + timedelta(seconds=2)
    fills = sim.on_market(
        22, MarketState(ts=t2, quote=make_quote("98.5", ask="98.55", bid="98.45", ts=t2))
    )
    assert fills and fills[0].price == Decimal("98.55")


def test_stop_triggers_then_market_fill_and_cancel() -> None:
    sim = _sim()
    o = sim.submit(
        make_intent(side=OrderSide.SELL, qty=10, order_type=OrderType.STOP, trigger=Decimal("95")),
        MarketState(ts=T0, quote=make_quote("100")),
    )
    t1 = T0 + timedelta(seconds=1)
    assert sim.on_market(22, MarketState(ts=t1, quote=make_quote("96", ts=t1))) == []
    t2 = T0 + timedelta(seconds=2)
    fills = sim.on_market(
        22, MarketState(ts=t2, quote=make_quote("94.8", bid="94.75", ask="94.85", ts=t2))
    )
    assert fills and fills[0].price == Decimal("94.75") and o.status == OrderStatus.FILLED
    # cancel on an open order
    o2 = sim.submit(
        make_intent(qty=5, order_type=OrderType.LIMIT, limit=Decimal("1")),
        MarketState(ts=t2, quote=make_quote("94.8")),
    )
    sim.cancel(o2.order_id, "user")
    assert o2.status == OrderStatus.CANCELLED


def test_idempotent_submit_and_closed_market_rejection() -> None:
    sim = _sim()
    i = make_intent(qty=1)
    a = sim.submit(i, MarketState(ts=T0, quote=make_quote("100")))
    b = sim.submit(i, MarketState(ts=T0, quote=make_quote("100")))
    assert a is b and len(sim.orders) == 1
    closed = T0.replace(hour=12)  # 17:30 IST
    r = sim.submit(make_intent(qty=1), MarketState(ts=closed, quote=make_quote("100", ts=closed)))
    assert r.status == OrderStatus.REJECTED


def test_determinism_with_stochastic_slippage() -> None:
    def run() -> list[Decimal]:
        sim = ExecutionSimulator(slippage=SpreadAwareSlippage(2, 0.5, seed=11), seed=11)
        out = []
        for i in range(5):
            t = T0 + timedelta(seconds=2 * i)
            sim.submit(
                make_intent(qty=75 * (i + 1)), MarketState(ts=t, quote=make_quote("100", ts=t))
            )
            t2 = t + timedelta(seconds=1)
            out += [
                f.price
                for f in sim.on_market(22, MarketState(ts=t2, quote=make_quote("100", ts=t2)))
            ]
        return out

    a, b = run(), run()
    assert a == b and len(a) == 5 and all(p > Decimal("100") for p in a)
