"""Proactive alerts (Mark 1 Stage 3.2, "EDITH without AI"): pure rules over facts.

Facts are gathered from Redis and the DB by `protocols.alert_store.gather_facts`; the rules
here are plain functions so each one is unit-tested without infrastructure. A rule yields
`AlertCandidate`s; storage applies the dedup window (`dedup`), so the same `dedup_key` is
never stored twice inside the window. Dedup keys carry the state that matters (e.g. "near"
vs "beyond" a PCR threshold), so an escalation is a new alert while a repeat is not.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

Severity = Literal["info", "warning", "critical"]

FEED_STALE_S = 120
TRADER_STALE_S = 180
BROKER_EXPIRY_WARN_MIN = 30
LOSS_WARN_FRACTION = Decimal("0.75")


@dataclass(frozen=True)
class AlertCandidate:
    kind: str
    severity: Severity
    title: str
    message: str
    dedup_key: str
    data: dict[str, Any] = field(default_factory=dict)
    instrument_id: int | None = None


@dataclass(frozen=True)
class PcrFact:
    symbol: str
    instrument_id: int | None
    pcr: Decimal | None
    ts: datetime | None
    expiry: str | None = None


@dataclass(frozen=True)
class FeedFact:
    present: bool
    state: str | None = None
    last_message_at: datetime | None = None
    provider: str | None = None
    is_demo: bool = False


@dataclass(frozen=True)
class BrokerFact:
    broker: str
    status: str  # valid | expired | revoked | missing
    expires_at: datetime | None = None


@dataclass(frozen=True)
class PaperLossFact:
    account_id: int
    name: str
    realized_today: Decimal
    initial_capital: Decimal
    max_daily_loss_pct: float


@dataclass(frozen=True)
class TraderFact:
    present: bool
    updated_at: datetime | None = None
    running_activations: int = 0


@dataclass(frozen=True)
class KillFact:
    scope: str
    reason: str | None
    by: str | None = None


@dataclass(frozen=True)
class AlertFacts:
    now: datetime
    market_open: bool
    pcr: tuple[PcrFact, ...] = ()
    feed: FeedFact | None = None
    brokers: tuple[BrokerFact, ...] = ()
    paper: tuple[PaperLossFact, ...] = ()
    trader: TraderFact | None = None
    kill: tuple[KillFact, ...] = ()


@dataclass(frozen=True)
class AlertParams:
    pcr_margin: Decimal = Decimal("0.1")
    pcr_no_put_buy_at: Decimal = Decimal("2.0")
    pcr_no_call_buy_at: Decimal = Decimal("0.5")
    pcr_max_age_minutes: int = 15


# ----------------------------------------------------------------------------- rules
def pcr_near_limit(f: AlertFacts, p: AlertParams) -> list[AlertCandidate]:
    """PCR within `pcr_margin` of a pcr_guard threshold, or beyond it. Stale or missing PCR
    is not judged here (feed_stale covers a silent feed)."""
    out: list[AlertCandidate] = []
    max_age = timedelta(minutes=p.pcr_max_age_minutes)
    for x in f.pcr:
        if x.pcr is None or x.ts is None or f.now - x.ts > max_age:
            continue
        side: str | None = None
        state = ""
        if x.pcr >= p.pcr_no_put_buy_at:
            side, state = "put", "beyond"
        elif x.pcr >= p.pcr_no_put_buy_at - p.pcr_margin:
            side, state = "put", "near"
        elif x.pcr <= p.pcr_no_call_buy_at:
            side, state = "call", "beyond"
        elif x.pcr <= p.pcr_no_call_buy_at + p.pcr_margin:
            side, state = "call", "near"
        if side is None:
            continue
        limit = p.pcr_no_put_buy_at if side == "put" else p.pcr_no_call_buy_at
        what = "PUT" if side == "put" else "CALL"
        if state == "beyond":
            title = f"{x.symbol} PCR {x.pcr:.2f}: {what} buys blocked"
            msg = f"PCR {x.pcr:.2f} is past the pcr_guard limit {limit}; {what} buys are blocked."
        else:
            title = f"{x.symbol} PCR {x.pcr:.2f} near the {what} limit"
            msg = (
                f"PCR {x.pcr:.2f} is within {p.pcr_margin} of the pcr_guard limit {limit}; "
                f"{what} buys will be blocked if it reaches {limit}."
            )
        out.append(
            AlertCandidate(
                kind="pcr_near_limit",
                severity="warning" if state == "beyond" else "info",
                title=title,
                message=msg,
                dedup_key=f"pcr_near_limit:{x.symbol}:{side}:{state}",
                data={
                    "symbol": x.symbol,
                    "pcr": str(x.pcr),
                    "limit": str(limit),
                    "state": state,
                    "snapshot_ts": x.ts.isoformat(),
                    "expiry": x.expiry,
                },
                instrument_id=x.instrument_id,
            )
        )
    return out


def feed_stale(f: AlertFacts, p: AlertParams) -> list[AlertCandidate]:
    """During market hours: collector silent > 120 s, not connected, or not reporting."""
    if not f.market_open:
        return []
    feed = f.feed
    if feed is None or not feed.present:
        return [
            AlertCandidate(
                kind="feed_stale",
                severity="critical",
                title="Market feed: collector not reporting",
                message="collector:health is missing in Redis; the collector is not running.",
                dedup_key="feed_stale:missing",
            )
        ]
    if feed.state != "connected":
        return [
            AlertCandidate(
                kind="feed_stale",
                severity="critical",
                title=f"Market feed {feed.state or 'unknown'}",
                message=f"Provider {feed.provider} is {feed.state} during market hours.",
                dedup_key=f"feed_stale:state:{feed.state}",
                data={"provider": feed.provider, "state": feed.state},
            )
        ]
    if feed.last_message_at is None:
        age = None
    else:
        age = int((f.now - feed.last_message_at).total_seconds())
    if age is None or age > FEED_STALE_S:
        return [
            AlertCandidate(
                kind="feed_stale",
                severity="warning",
                title="Market feed stale",
                message=(
                    "No market message received yet."
                    if age is None
                    else f"Last market message {age} s ago (limit {FEED_STALE_S} s)."
                ),
                dedup_key="feed_stale:silent",
                data={"provider": feed.provider, "last_message_age_s": age},
            )
        ]
    return []


def broker_session(f: AlertFacts, p: AlertParams) -> list[AlertCandidate]:
    """A configured broker whose session is not valid, or expires within 30 minutes."""
    out: list[AlertCandidate] = []
    for b in f.brokers:
        if b.status != "valid":
            out.append(
                AlertCandidate(
                    kind="broker_session",
                    severity="critical",
                    title=f"{b.broker.title()} session {b.status}",
                    message=f"The {b.broker} session is {b.status}; log in on Settings > Brokers.",
                    dedup_key=f"broker_session:{b.broker}:{b.status}",
                    data={"broker": b.broker, "status": b.status},
                )
            )
        elif b.expires_at is not None:
            mins = int((b.expires_at - f.now).total_seconds() // 60)
            if mins <= BROKER_EXPIRY_WARN_MIN:
                out.append(
                    AlertCandidate(
                        kind="broker_session",
                        severity="warning",
                        title=f"{b.broker.title()} session expires in {max(mins, 0)} min",
                        message=f"The {b.broker} session expires at {b.expires_at.isoformat()}.",
                        dedup_key=f"broker_session:{b.broker}:expiring",
                        data={"broker": b.broker, "expires_at": b.expires_at.isoformat()},
                    )
                )
    return out


def daily_loss_near(f: AlertFacts, p: AlertParams) -> list[AlertCandidate]:
    """Paper account realised loss today >= 75 % of its daily loss limit (critical at 100 %)."""
    out: list[AlertCandidate] = []
    for a in f.paper:
        cap = a.initial_capital * Decimal(str(a.max_daily_loss_pct)) / 100
        if cap <= 0 or a.realized_today >= 0:
            continue
        used = -a.realized_today / cap
        if used < LOSS_WARN_FRACTION:
            continue
        hit = used >= 1
        pct = int(used * 100)
        out.append(
            AlertCandidate(
                kind="daily_loss_near",
                severity="critical" if hit else "warning",
                title=f"{a.name}: daily loss {'limit hit' if hit else f'at {pct}% of limit'}",
                message=(
                    f"Realised today {a.realized_today:.2f} against a daily limit of "
                    f"-{cap:.2f} ({a.max_daily_loss_pct}% of {a.initial_capital:.2f})."
                ),
                dedup_key=f"daily_loss_near:{a.account_id}:{'hit' if hit else 'near'}",
                data={
                    "paper_account_id": a.account_id,
                    "realized_today": str(a.realized_today),
                    "limit": str(-cap),
                    "used_pct": pct,
                },
            )
        )
    return out


def kill_switch_active(f: AlertFacts, p: AlertParams) -> list[AlertCandidate]:
    return [
        AlertCandidate(
            kind="kill_switch_active",
            severity="warning",
            title=f"Kill switch ON ({k.scope})",
            message=f"New entries are blocked. Reason: {k.reason or 'not given'}.",
            dedup_key=f"kill_switch_active:{k.scope}",
            data={"scope": k.scope, "reason": k.reason, "by": k.by},
        )
        for k in f.kill
    ]


def trader_down(f: AlertFacts, p: AlertParams) -> list[AlertCandidate]:
    """During market hours: trader:health missing or older than 3 minutes."""
    if not f.market_open:
        return []
    t = f.trader
    age = None
    if t is not None and t.present and t.updated_at is not None:
        age = int((f.now - t.updated_at).total_seconds())
        if age <= TRADER_STALE_S:
            return []
    running = t.running_activations if t is not None else 0
    return [
        AlertCandidate(
            kind="trader_down",
            severity="critical" if running else "warning",
            title="Paper trader not running",
            message=(
                "trader:health is missing in Redis."
                if age is None
                else f"trader:health last written {age} s ago (limit {TRADER_STALE_S} s)."
            )
            + (f" {running} paper strategies are not being run." if running else ""),
            dedup_key="trader_down",
            data={"age_s": age, "running_activations": running},
        )
    ]


RULES = (
    pcr_near_limit,
    feed_stale,
    broker_session,
    daily_loss_near,
    kill_switch_active,
    trader_down,
)


def evaluate(f: AlertFacts, p: AlertParams) -> list[AlertCandidate]:
    out: list[AlertCandidate] = []
    for rule in RULES:
        out.extend(rule(f, p))
    return out


# ----------------------------------------------------------------------------- dedup
def dedup(
    candidates: Iterable[AlertCandidate],
    last_seen: dict[str, datetime],
    now: datetime,
    window: timedelta,
) -> list[AlertCandidate]:
    """Candidates to store now: drops any whose key was stored within `window` before `now`
    (per `last_seen`) and repeats of a key inside this batch. `last_seen` is updated."""
    out: list[AlertCandidate] = []
    for c in candidates:
        prev = last_seen.get(c.dedup_key)
        if prev is not None and now - prev < window:
            continue
        last_seen[c.dedup_key] = now
        out.append(c)
    return out
