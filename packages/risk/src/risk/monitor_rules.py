"""Deterministic monitor rules (no LLM). Inputs are plain numbers; outputs say what to do.
The execution monitor job evaluates these every few seconds during the session."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class MonitorAction(StrEnum):
    NONE = "none"
    WARN = "warn"
    KILL_ACCOUNT = "kill_account"
    KILL_GLOBAL = "kill_global"


@dataclass(frozen=True)
class MonitorInput:
    feed_silent_s: float | None  # seconds since last market message; None = never connected
    market_open: bool
    open_positions: int
    reconciliation_mismatch: bool
    realized_today: Decimal
    daily_loss_cap: Decimal  # positive number
    feed_silent_threshold_s: float = 60.0


@dataclass(frozen=True)
class MonitorVerdict:
    action: MonitorAction
    reasons: tuple[str, ...]


def evaluate(inp: MonitorInput) -> MonitorVerdict:
    reasons: list[str] = []
    action = MonitorAction.NONE

    def escalate(a: MonitorAction, why: str) -> None:
        nonlocal action
        reasons.append(why)
        order = [
            MonitorAction.NONE,
            MonitorAction.WARN,
            MonitorAction.KILL_ACCOUNT,
            MonitorAction.KILL_GLOBAL,
        ]
        if order.index(a) > order.index(action):
            action = a

    if inp.market_open and inp.open_positions > 0:
        if inp.feed_silent_s is None:
            escalate(MonitorAction.KILL_GLOBAL, "feed never connected with open positions")
        elif inp.feed_silent_s > inp.feed_silent_threshold_s:
            escalate(
                MonitorAction.KILL_GLOBAL,
                f"feed silent {inp.feed_silent_s:.0f}s with open positions",
            )
    if inp.reconciliation_mismatch:
        escalate(MonitorAction.KILL_ACCOUNT, "broker reconciliation mismatch")
    if inp.daily_loss_cap > 0:
        loss = -inp.realized_today
        if loss >= inp.daily_loss_cap:
            escalate(MonitorAction.KILL_ACCOUNT, "daily loss limit reached")
        elif loss >= inp.daily_loss_cap * Decimal("0.9"):
            escalate(MonitorAction.WARN, "daily loss at 90% of limit")
    return MonitorVerdict(action, tuple(reasons))
