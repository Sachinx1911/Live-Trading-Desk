from datetime import UTC, datetime
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from core.calendar import nse_calendar
from core.models import OrderSide, Position, ProductType, Quote, Segment, Signal, TradingMode
from risk.engine import RiskEngine
from risk.limits import AccountState, InstrumentMeta, RiskLimits
from risk.sizing import size_order

CAL = nse_calendar()
NOW = datetime(2026, 11, 17, 5, 0, tzinfo=UTC)  # 10:30 IST, Tuesday
NIFTY_FUT = InstrumentMeta(
    instrument_id=30,
    symbol="NIFTY26NOVFUT",
    segment=Segment.FUTURES,
    lot_size=75,
    freeze_quantity=1800,
    underlying_symbol="NIFTY",
)
STOCK = InstrumentMeta(instrument_id=5, symbol="RELIANCE", segment=Segment.EQUITY, lot_size=1)


def sig(
    side: OrderSide = OrderSide.BUY,
    kind: str = "entry",
    ref: str = "2400",
    stop: str | None = "2350",
    qty: int | None = None,
    instrument_id: int = 30,
) -> Signal:
    return Signal(
        strategy_version_id=1,
        instrument_id=instrument_id,
        ts=NOW,
        side=side,
        kind=kind,
        reason="test",
        reference_price=Decimal(ref),
        stop_price=Decimal(stop) if stop else None,
        suggested_quantity=qty,
    )


def acct(equity: str = "1000000", **kw) -> AccountState:
    return AccountState(account_id=1, equity=Decimal(equity), cash=Decimal(equity), **kw)


def quote(px: str = "2400") -> Quote:
    p = Decimal(px)
    return Quote(
        instrument_id=30,
        ts=NOW,
        ltp=p,
        bid=p - Decimal("0.05"),
        ask=p + Decimal("0.05"),
        provider_id="fake",
        received_at=NOW,
    )


# ---------------------------------------------------------------- sizing
def test_risk_percent_sizing_rounds_to_lots() -> None:
    # 1% of 10L = 10,000; stop 50 pts -> 200 units -> 2 lots of 75 = 150
    r = size_order(sig(), RiskLimits(), acct(), NIFTY_FUT, Decimal("2400"))
    assert r.lots == 2 and r.quantity == 150 and r.risk_amount == Decimal(7500)
    assert r.reason == "risk_percent"


def test_sizing_one_lot_when_budget_covers_it() -> None:
    # budget 1,000; stop 10 pts -> 100 units -> 1 lot of 75
    r = size_order(sig(stop="2390"), RiskLimits(), acct("100000"), NIFTY_FUT, Decimal("2400"))
    assert r.lots == 1


def test_sizing_zero_when_one_lot_too_risky() -> None:
    r = size_order(sig(stop="1400"), RiskLimits(), acct("100000"), NIFTY_FUT, Decimal("2400"))
    assert r.quantity == 0


def test_suggested_quantity_is_a_cap() -> None:
    r = size_order(sig(qty=75), RiskLimits(), acct(), NIFTY_FUT, Decimal("2400"))
    assert r.quantity == 75 and r.reason == "suggested_quantity_cap"


def test_drawdown_halves_size() -> None:
    a = acct("850000", peak_equity=Decimal("1000000"))
    r = size_order(sig(), RiskLimits(), a, NIFTY_FUT, Decimal("2400"))
    assert "drawdown: size halved" in r.notes
    assert r.lots == 1  # 8,500*0.5 = 4,250 / 50 = 85 -> 1 lot


def test_max_lots_cap() -> None:
    r = size_order(
        sig(stop="2399"), RiskLimits(max_lots_per_order=3), acct(), NIFTY_FUT, Decimal("2400")
    )
    assert r.lots == 3 and r.reason == "max_lots_per_order"


# ---------------------------------------------------------------- engine
def evaluate(signal: Signal, account: AccountState, limits: RiskLimits | None = None, **kw):
    eng = RiskEngine(limits or RiskLimits())
    return eng.evaluate(
        signal,
        account,
        NIFTY_FUT,
        quote(),
        now=kw.pop("now", NOW),
        calendar=CAL,
        kill_switch_active=kw.pop("kill", False),
        mode=TradingMode.PAPER,
        **kw,
    )


def test_entry_allowed_builds_intent() -> None:
    d = evaluate(sig(), acct())
    assert d.allowed and d.intent is not None
    assert d.intent.quantity == 150 and d.intent.product == ProductType.INTRADAY
    assert d.intent.idempotency_key.startswith("1:")


@pytest.mark.parametrize(
    "kw, needle",
    [
        ({"kill": True}, "kill switch"),
        ({"now": datetime(2026, 11, 17, 9, 30, tzinfo=UTC)}, "outside entry window"),  # 15:00 IST
        ({"now": datetime(2026, 11, 15, 5, 0, tzinfo=UTC)}, "market closed"),  # Sunday
        ({"events_today": ["RBI policy"]}, "high-impact event"),
    ],
)
def test_entry_rejections(kw, needle) -> None:
    d = evaluate(sig(), acct(), **kw)
    assert not d.allowed and any(needle in r for r in d.reasons)


def test_daily_and_weekly_loss_block_entries() -> None:
    d = evaluate(sig(), acct(realized_today=Decimal("-20000")))
    assert "daily loss limit breached" in d.reasons
    d = evaluate(sig(), acct(realized_week=Decimal("-50000")))
    assert "weekly loss limit breached" in d.reasons


def test_max_positions_and_short_and_product() -> None:
    pos = tuple(
        Position(
            account_id=1, mode=TradingMode.PAPER, instrument_id=i, quantity=75, avg_price=Decimal(1)
        )
        for i in (1, 2, 3)
    )
    d = evaluate(sig(), acct(open_positions=pos))
    assert any("max open positions" in r for r in d.reasons)
    d = evaluate(sig(side=OrderSide.SELL), acct(), RiskLimits(allow_short=False))
    assert "short entries disabled" in d.reasons
    d = evaluate(sig(), acct(), RiskLimits(allowed_products=frozenset({ProductType.DELIVERY})))
    assert any("not allowed" in r for r in d.reasons)


def test_exposure_and_correlated_caps() -> None:
    a = acct("100000", exposure=Decimal("150000"))
    d = evaluate(sig(stop="2399"), a)  # notional would exceed 200%
    assert any("exposure" in r for r in d.reasons)
    a = acct(exposure_by_key={"NIFTY": Decimal("990000")})
    d = evaluate(sig(), a)
    assert any("correlated" in r for r in d.reasons)


def test_all_failing_reasons_collected() -> None:
    d = evaluate(
        sig(side=OrderSide.SELL),
        acct(realized_today=Decimal("-99999")),
        RiskLimits(allow_short=False),
        kill=True,
    )
    assert len(d.reasons) >= 3


def test_exit_allowed_even_when_daily_loss_breached() -> None:
    pos = (
        Position(
            account_id=1,
            mode=TradingMode.PAPER,
            instrument_id=30,
            quantity=150,
            avg_price=Decimal("2400"),
        ),
    )
    a = acct(realized_today=Decimal("-99999"), open_positions=pos)
    d = evaluate(sig(side=OrderSide.SELL, kind="stop", stop=None), a, kill=True)
    assert d.allowed and d.intent is not None and d.intent.quantity == 150


def test_exit_without_position_or_wrong_side_rejected() -> None:
    assert not evaluate(sig(side=OrderSide.SELL, kind="exit"), acct()).allowed
    pos = (
        Position(
            account_id=1,
            mode=TradingMode.PAPER,
            instrument_id=30,
            quantity=75,
            avg_price=Decimal(1),
        ),
    )
    assert not evaluate(sig(side=OrderSide.BUY, kind="exit"), acct(open_positions=pos)).allowed


@settings(max_examples=150, deadline=None)
@given(
    equity=st.integers(100_000, 50_000_000),
    stop_pts=st.integers(1, 400),
    exposure=st.integers(0, 10_000_000),
    max_lots=st.integers(1, 20),
)
def test_allowed_entries_respect_caps(
    equity: int, stop_pts: int, exposure: int, max_lots: int
) -> None:
    limits = RiskLimits(max_lots_per_order=max_lots)
    a = acct(str(equity), exposure=Decimal(exposure))
    s = sig(stop=str(2400 - stop_pts))
    d = RiskEngine(limits).evaluate(
        s, a, NIFTY_FUT, quote(), now=NOW, calendar=CAL, kill_switch_active=False
    )
    if d.allowed:
        assert d.sizing is not None and d.intent is not None
        assert d.sizing.lots <= max_lots
        assert d.sizing.quantity % NIFTY_FUT.lot_size == 0
        assert d.sizing.risk_amount <= Decimal(equity) * Decimal("0.01")
        assert Decimal(exposure) + d.sizing.notional <= Decimal(equity) * 2
        assert d.sizing.quantity <= 1800
