"""Gathering alert facts, storing alerts with the dedup window, and delivering them.

Delivery is recorded per alert in `delivered`: {"in_app": true, "telegram": "sent" |
"skipped" | "failed" | "pending"}. "pending" is written by processes that must not block on
HTTP (the paper trader); the worker's alert job delivers pending alerts on its next run.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import orjson
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import Alert, PaperAccount, PaperTrade, RiskLimit, StrategyActivation
from core.db.models._enums import ActivationStatus, RiskLimitScope
from core.logging import get_logger
from core.notify import Notifier
from core.secrets import SecretBox
from core.settings import Settings
from core.time import ensure_utc
from market_data.repo.chains import latest_chain_oi
from market_data.repo.instruments import get_by_symbol
from protocols.actions import broker_rows, ist_day_bounds
from protocols.alerts import (
    AlertCandidate,
    AlertFacts,
    AlertParams,
    BrokerFact,
    FeedFact,
    KillFact,
    PaperLossFact,
    PcrFact,
    TraderFact,
    dedup,
)
from protocols.context import ActionContext
from protocols.jsonable import jsonable
from risk.limits import RiskLimits
from risk.owner_rules import pcr_from_oi

log = get_logger(__name__)


def params_from(settings: Settings) -> AlertParams:
    lim = RiskLimits()
    return AlertParams(
        pcr_margin=Decimal(str(settings.alert_pcr_margin)),
        pcr_no_put_buy_at=Decimal(str(lim.pcr_no_put_buy_at)),
        pcr_no_call_buy_at=Decimal(str(lim.pcr_no_call_buy_at)),
        pcr_max_age_minutes=lim.pcr_max_age_minutes,
    )


def telegram_configured(settings: Settings) -> bool:
    return bool(settings.telegram_bot_token.get_secret_value() and settings.telegram_chat_id)


def _loads(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    try:
        v = orjson.loads(raw)
    except orjson.JSONDecodeError:
        return None
    return v if isinstance(v, dict) else None


def _ts(v: Any) -> datetime | None:
    try:
        return ensure_utc(str(v)) if v else None
    except ValueError:
        return None


async def gather_facts(
    db: AsyncSession,
    redis: Any,
    settings: Settings,
    *,
    now: datetime,
    market_open: bool,
    secret_box: SecretBox | None,
    notifier: Notifier,
) -> AlertFacts:
    """Read everything the rules need. Missing data stays missing (rules skip or report it)."""
    # PCR of the chain underlyings
    pcr: list[PcrFact] = []
    for sym in [s.strip().upper() for s in settings.collect_chain_underlyings.split(",")]:
        if not sym:
            continue
        ins = await get_by_symbol(db, "NSE", sym)
        if ins is None:
            continue
        oi = await latest_chain_oi(db, ins.instrument_id, now)
        if oi is None:
            pcr.append(PcrFact(sym, ins.instrument_id, None, None))
            continue
        pcr.append(
            PcrFact(
                sym,
                ins.instrument_id,
                pcr_from_oi(oi.put_oi, oi.call_oi),
                ensure_utc(oi.ts),
                oi.expiry.date().isoformat(),
            )
        )
    # collector
    ch = _loads(await redis.get("collector:health"))
    feed = (
        FeedFact(present=False)
        if ch is None
        else FeedFact(
            present=True,
            state=str(ch.get("state")) if ch.get("state") else None,
            last_message_at=_ts(ch.get("last_message_at")),
            provider=ch.get("provider"),
            is_demo=bool(ch.get("is_demo")),
        )
    )
    # brokers: only accounts that exist (an unconfigured broker is not an alert)
    ctx = ActionContext(db, redis, settings, notifier, user_id=None, secret_box=secret_box)
    brokers = tuple(
        BrokerFact(r["broker"], r["status"], _ts(r.get("expires_at")))
        for r in await broker_rows(ctx, now)
        if r.get("account_id") is not None
    )
    # paper accounts: realised today against the daily loss limit
    day_start, _ = ist_day_bounds(now)
    paper: list[PaperLossFact] = []
    accounts = (
        (await db.execute(select(PaperAccount).where(PaperAccount.is_active.is_(True))))
        .scalars()
        .all()
    )
    for a in accounts:
        realized = Decimal(
            (
                await db.execute(
                    select(func.coalesce(func.sum(PaperTrade.net_pnl), 0)).where(
                        PaperTrade.paper_account_id == a.id, PaperTrade.exit_at >= day_start
                    )
                )
            ).scalar_one()
        )
        row = (
            await db.execute(
                select(RiskLimit.limits).where(
                    RiskLimit.scope == RiskLimitScope.PAPER_ACCOUNT,
                    RiskLimit.scope_id == a.id,
                    RiskLimit.is_active.is_(True),
                )
            )
        ).scalar_one_or_none()
        lim = RiskLimits.model_validate(row) if row else RiskLimits()
        paper.append(
            PaperLossFact(a.id, a.name, realized, a.initial_capital, lim.max_daily_loss_pct)
        )
    # trader
    th = _loads(await redis.get("trader:health"))
    running = (
        await db.execute(
            select(func.count(StrategyActivation.id)).where(
                StrategyActivation.paper_account_id.is_not(None),
                StrategyActivation.status == ActivationStatus.ACTIVE,
            )
        )
    ).scalar_one()
    trader = TraderFact(
        present=th is not None,
        updated_at=_ts(th.get("updated_at")) if th else None,
        running_activations=int(running),
    )
    # kill switches (every scope that is set)
    kill: list[KillFact] = []
    async for key in redis.scan_iter(match="kill:*"):
        k = key.decode() if isinstance(key, bytes | bytearray) else str(key)
        detail = _loads(await redis.get(k)) or {}
        kill.append(KillFact(k.removeprefix("kill:"), detail.get("reason"), detail.get("by")))
    kill.sort(key=lambda x: x.scope)
    return AlertFacts(
        now=now,
        market_open=market_open,
        pcr=tuple(pcr),
        feed=feed,
        brokers=brokers,
        paper=tuple(paper),
        trader=trader,
        kill=tuple(kill),
    )


async def store_alerts(
    db: AsyncSession,
    candidates: Iterable[AlertCandidate],
    *,
    now: datetime,
    window: timedelta,
    telegram: str = "skipped",
) -> list[Alert]:
    """Insert candidates whose dedup key was not stored inside `window`. The caller commits."""
    cands = list(candidates)
    if not cands:
        return []
    keys = sorted({c.dedup_key for c in cands})
    rows = await db.execute(
        select(Alert.dedup_key, func.max(Alert.ts))
        .where(Alert.dedup_key.in_(keys), Alert.ts > now - window)
        .group_by(Alert.dedup_key)
    )
    last_seen: dict[str, datetime] = {k: ensure_utc(ts) for k, ts in rows.all()}
    stored: list[Alert] = []
    for c in dedup(cands, last_seen, now, window):
        a = Alert(
            ts=now,
            kind=c.kind,
            severity=c.severity,
            title=c.title,
            message=c.message,
            data=jsonable(c.data),
            dedup_key=c.dedup_key,
            instrument_id=c.instrument_id,
            delivered={"in_app": True, "telegram": telegram},
        )
        db.add(a)
        stored.append(a)
    await db.flush()
    return stored


async def deliver(
    alerts: Iterable[Alert], notifier: Notifier, *, configured: bool
) -> dict[str, int]:
    """Send to Telegram when configured; record the outcome on each alert row."""
    counts = {"sent": 0, "failed": 0, "skipped": 0}
    for a in alerts:
        if not configured:
            outcome = "skipped"
        else:
            ok = await notifier.send(f"{a.title}\n{a.message}", level=a.severity)
            outcome = "sent" if ok else "failed"
        a.delivered = {**(a.delivered or {}), "in_app": True, "telegram": outcome}
        counts[outcome] += 1
    return counts


async def pending_alerts(db: AsyncSession, limit: int = 50) -> list[Alert]:
    q = (
        select(Alert)
        .where(Alert.delivered["telegram"].astext == "pending")
        .order_by(Alert.ts)
        .limit(limit)
    )
    return list((await db.execute(q)).scalars().all())


async def record_alert(
    db: AsyncSession, c: AlertCandidate, *, now: datetime, window: timedelta
) -> Alert | None:
    """Store one alert from a process that must not block on HTTP (the paper trader);
    Telegram delivery is left `pending` for the worker's alert job."""
    stored = await store_alerts(db, [c], now=now, window=window, telegram="pending")
    return stored[0] if stored else None
