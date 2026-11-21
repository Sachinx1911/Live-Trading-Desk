"""Owner trading rules. Rule 1: pcr_guard (docs/trading-rules.md)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from core.calendar import nse_calendar
from core.models import OptionType, OrderSide, Position, Quote, Segment, Signal, TradingMode
from risk.engine import RiskEngine
from risk.limits import AccountState, InstrumentMeta, RiskLimits
from risk.owner_rules import OWNER_RULES, MarketContext, pcr_from_oi

CAL = nse_calendar()
NOW = datetime(2026, 11, 17, 5, 0, tzinfo=UTC)  # 10:30 IST, Tuesday


def opt(option_type: OptionType | None, iid: int = 40) -> InstrumentMeta:
    return InstrumentMeta(
        instrument_id=iid,
        symbol=f"NIFTY25200{option_type or 'XX'}",
        segment=Segment.OPTIONS,
        lot_size=65,
        underlying_symbol="NIFTY",
        option_type=option_type,
    )


FUT = InstrumentMeta(
    instrument_id=30,
    symbol="NIFTYFUT",
    segment=Segment.FUTURES,
    lot_size=65,
    underlying_symbol="NIFTY",
)


def sig(side: OrderSide = OrderSide.BUY, kind: str = "entry", iid: int = 40) -> Signal:
    return Signal(
        strategy_version_id=1,
        instrument_id=iid,
        ts=NOW,
        side=side,
        kind=kind,
        reason="test",
        reference_price=Decimal("100"),
        stop_price=Decimal("90") if side == OrderSide.BUY else Decimal("110"),
    )


def ctx(pcr: str | None, age_min: int = 1) -> MarketContext:
    return MarketContext(
        now=NOW,
        pcr=Decimal(pcr) if pcr is not None else None,
        pcr_ts=NOW - timedelta(minutes=age_min) if pcr is not None else None,
    )


def run(meta: InstrumentMeta, signal: Signal, market: MarketContext | None, **acct_kw):
    account = AccountState(
        account_id=1, equity=Decimal("1000000"), cash=Decimal("1000000"), **acct_kw
    )
    q = Quote(
        instrument_id=meta.instrument_id,
        ts=NOW,
        ltp=Decimal("100"),
        bid=Decimal("99.95"),
        ask=Decimal("100.05"),
        provider_id="fake",
        received_at=NOW,
    )
    return RiskEngine(RiskLimits()).evaluate(
        signal,
        account,
        meta,
        q,
        now=NOW,
        calendar=CAL,
        kill_switch_active=False,
        mode=TradingMode.PAPER,
        market=market,
    )


def test_rule_is_registered() -> None:
    assert [r.code for r in OWNER_RULES] == ["pcr_guard"]


@pytest.mark.parametrize(
    ("option_type", "pcr", "allowed"),
    [
        (OptionType.PE, "2.00", False),  # put writers double -> never buy a put
        (OptionType.PE, "2.75", False),
        (OptionType.PE, "1.99", True),
        (OptionType.PE, "0.40", True),  # bearish chain: put buy is fine
        (OptionType.CE, "0.50", False),  # call writers double -> never buy a call
        (OptionType.CE, "0.31", False),
        (OptionType.CE, "0.51", True),
        (OptionType.CE, "2.40", True),  # bullish chain: call buy is fine
    ],
)
def test_pcr_guard_thresholds(option_type: OptionType, pcr: str, allowed: bool) -> None:
    d = run(opt(option_type), sig(), ctx(pcr))
    assert d.allowed is allowed
    if allowed:
        assert "pcr_guard" in d.checks
    else:
        assert d.intent is None
        assert any("PCR" in r for r in d.reasons)


def test_missing_or_stale_pcr_blocks_option_buys() -> None:
    assert not run(opt(OptionType.PE), sig(), ctx(None)).allowed
    stale = run(opt(OptionType.CE), sig(), ctx("1.0", age_min=16))
    assert not stale.allowed and "min old" in stale.reasons[0]
    assert run(opt(OptionType.CE), sig(), ctx("1.0", age_min=15)).allowed


def test_unknown_option_type_blocks() -> None:
    assert not run(opt(None), sig(), ctx("1.0")).allowed


def test_no_context_is_recorded_as_skipped() -> None:
    d = run(opt(OptionType.PE), sig(), None)
    assert d.allowed and "pcr_guard:skipped" in d.checks


def test_rule_does_not_touch_non_option_or_sell_entries() -> None:
    assert run(FUT, sig(iid=30), ctx("3.0")).allowed
    d = run(opt(OptionType.PE), sig(side=OrderSide.SELL), ctx("3.0"))
    assert not any("PCR" in r for r in d.reasons)


def test_exit_of_a_long_put_is_never_blocked() -> None:
    pos = Position(
        instrument_id=40,
        quantity=65,
        avg_price=Decimal("100"),
        mode=TradingMode.PAPER,
        account_id=1,
    )
    d = run(
        opt(OptionType.PE),
        sig(side=OrderSide.SELL, kind="exit"),
        ctx("3.0"),
        open_positions=(pos,),
    )
    assert d.allowed


def test_pcr_from_oi() -> None:
    assert pcr_from_oi(200, 100) == Decimal("2.0000")
    assert pcr_from_oi(50, 100) == Decimal("0.5000")
    assert pcr_from_oi(10, 0) is None


@given(
    pcr=st.decimals(min_value="0.01", max_value="10", places=2),
    option_type=st.sampled_from([OptionType.CE, OptionType.PE]),
)
def test_invariant_no_put_buy_above_2_no_call_buy_below_half(
    pcr: Decimal, option_type: OptionType
) -> None:
    d = run(opt(option_type), sig(), ctx(str(pcr)))
    if option_type == OptionType.PE and pcr >= 2:
        assert not d.allowed
    if option_type == OptionType.CE and pcr <= Decimal("0.5"):
        assert not d.allowed
    if Decimal("0.5") < pcr < 2:
        assert d.allowed
