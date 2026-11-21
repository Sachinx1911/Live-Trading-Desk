"""Owner trading rules: hard, named, deterministic blocks on new entries.

These are the product owner's own market rules, kept apart from the numeric risk limits
so each one is a single small function with a name, a description and tests. The risk
engine runs every registered rule on every entry signal, in every mode; a rule can only
block, never create or resize an order. Exits are never blocked.

To add a rule: write a function `(signal, instrument, market, limits) -> RuleOutcome`,
decorate it with `@owner_rule(code, description)`, add tests, and list it in
`docs/trading-rules.md`.

Data the rules need (PCR, later: OI build-up, VIX, ...) arrives in `MarketContext`,
built by the caller from stored market data. When the caller passes no context at all
(backtest / replay, where the history of that data does not exist yet) rules that need
it report `skipped`; when a context is passed but the value is missing or stale, the
rule blocks: with a live account, no data means no trade.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal

from core.models import OptionType, OrderSide, Segment, Signal
from risk.limits import InstrumentMeta, RiskLimits


@dataclass(frozen=True)
class MarketContext:
    """Market facts for owner rules, for the underlying of the instrument being traded."""

    now: datetime
    pcr: Decimal | None = None  # total put OI / total call OI, near expiry
    pcr_ts: datetime | None = None
    pcr_expiry: str | None = None


@dataclass(frozen=True)
class RuleOutcome:
    status: Literal["pass", "block", "skipped", "not_applicable"]
    message: str = ""


RuleFn = Callable[[Signal, InstrumentMeta, MarketContext | None, RiskLimits], RuleOutcome]


@dataclass(frozen=True)
class OwnerRule:
    code: str
    description: str
    fn: RuleFn


OWNER_RULES: list[OwnerRule] = []


def owner_rule(code: str, description: str) -> Callable[[RuleFn], RuleFn]:
    def deco(fn: RuleFn) -> RuleFn:
        if any(r.code == code for r in OWNER_RULES):
            raise ValueError(f"duplicate owner rule {code}")
        OWNER_RULES.append(OwnerRule(code, description, fn))
        return fn

    return deco


PASS = RuleOutcome("pass")
NOT_APPLICABLE = RuleOutcome("not_applicable")


@owner_rule(
    "pcr_guard",
    "Never buy a PUT when put writers are at least double the call writers (PCR >= 2); "
    "never buy a CALL when call writers are at least double the put writers (PCR <= 0.5).",
)
def pcr_guard(
    signal: Signal, instrument: InstrumentMeta, market: MarketContext | None, limits: RiskLimits
) -> RuleOutcome:
    if instrument.segment != Segment.OPTIONS or signal.side != OrderSide.BUY:
        return NOT_APPLICABLE
    if instrument.option_type is None:
        return RuleOutcome("block", "option type unknown; PCR rule cannot be checked")
    if market is None:
        return RuleOutcome("skipped", "no option-chain history in this mode")
    if market.pcr is None or market.pcr_ts is None:
        return RuleOutcome("block", "no PCR available for the underlying; option buy blocked")
    age = market.now - market.pcr_ts
    if age > timedelta(minutes=limits.pcr_max_age_minutes):
        mins = int(age.total_seconds() // 60)
        return RuleOutcome("block", f"PCR is {mins} min old; option buy blocked")
    pcr = market.pcr
    if instrument.option_type == OptionType.PE and pcr >= Decimal(str(limits.pcr_no_put_buy_at)):
        return RuleOutcome(
            "block",
            f"PCR {pcr:.2f} >= {limits.pcr_no_put_buy_at}: put writers dominate, no PUT buy",
        )
    if instrument.option_type == OptionType.CE and pcr <= Decimal(str(limits.pcr_no_call_buy_at)):
        return RuleOutcome(
            "block",
            f"PCR {pcr:.2f} <= {limits.pcr_no_call_buy_at}: call writers dominate, no CALL buy",
        )
    return PASS


def pcr_from_oi(put_oi: int, call_oi: int) -> Decimal | None:
    """Put/call ratio by open interest; None when there is no call OI to divide by."""
    if call_oi <= 0 or put_oi < 0:
        return None
    return (Decimal(put_oi) / Decimal(call_oi)).quantize(Decimal("0.0001"))


def evaluate_owner_rules(
    signal: Signal,
    instrument: InstrumentMeta,
    market: MarketContext | None,
    limits: RiskLimits,
) -> list[tuple[str, RuleOutcome]]:
    return [(r.code, r.fn(signal, instrument, market, limits)) for r in OWNER_RULES]


__all__ = [
    "OWNER_RULES",
    "MarketContext",
    "OwnerRule",
    "RuleOutcome",
    "evaluate_owner_rules",
    "owner_rule",
    "pcr_from_oi",
]
