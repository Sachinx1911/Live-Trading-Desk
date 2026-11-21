"""The registered actions (seed of the Stage 4 tool catalogue).

Every number an action returns comes from a stored row or a Redis key written by the
process that owns it; when the data is missing the result says so instead of inventing a
value (CLAUDE.md rule 5). No action places, modifies or cancels an order.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import orjson
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, text

from core.calendar import nse_calendar
from core.db.models import (
    Alert,
    BrokerAccount,
    DataProvider,
    Event,
    Instrument,
    KillSwitchEvent,
    OptionChainSnapshot,
    PaperAccount,
    PaperPosition,
    PaperTrade,
    StrategyActivation,
)
from core.db.models._enums import ActivationStatus, KillSwitchAction, KillSwitchScope
from core.services.audit import write_audit
from core.services.brokers import SUPPORTED, BrokerError, BrokerService
from core.services.paper import running_paper_activations, stop_activation
from core.time import IST, ensure_utc
from market_data.repo.chains import latest_chain_oi
from market_data.repo.instruments import get_by_symbol
from market_data.repo.regime import latest_daily, latest_intraday
from protocols.context import ActionContext
from protocols.registry import ActionError, ActionRegistry, NoArgs
from risk.kill_switch import KillSwitch
from risk.limits import RiskLimits
from risk.owner_rules import pcr_from_oi

REGISTRY = ActionRegistry()

COLLECTOR_STALE_S = 120  # feed silent longer than this during the session = stale
TRADER_STALE_S = 180  # trader writes its health every 60 s
WORKER_STALE_S = 600  # heartbeat cron runs every 5 min
CHAIN_SYMBOLS = ["NIFTY", "BANKNIFTY"]
SYMBOL_PATTERN = r"^[A-Z0-9&_\-]{1,32}$"


# ----------------------------------------------------------------------------- helpers
def _age_s(ts: datetime | None, now: datetime) -> int | None:
    return None if ts is None else int((now - ensure_utc(ts)).total_seconds())


def _parse_ts(v: Any) -> datetime | None:
    if not v:
        return None
    try:
        return ensure_utc(str(v))
    except ValueError:
        return None


async def _redis_json(ctx: ActionContext, key: str) -> dict[str, Any] | None:
    raw = await ctx.redis.get(key)
    if raw is None:
        return None
    try:
        val = orjson.loads(raw)
    except orjson.JSONDecodeError:
        return None
    return val if isinstance(val, dict) else None


def ist_day_bounds(now: datetime) -> tuple[datetime, datetime]:
    day = now.astimezone(IST).date()
    start = datetime.combine(day, datetime.min.time(), tzinfo=IST)
    return ensure_utc(start), ensure_utc(start + timedelta(days=1))


async def collector_status(ctx: ActionContext, now: datetime, market_open: bool) -> dict[str, Any]:
    h = await _redis_json(ctx, "collector:health")
    if h is None:
        return {
            "status": "missing",
            "message": "collector:health not in Redis (collector not running)",
        }
    last = _parse_ts(h.get("last_message_at"))
    age = _age_s(last, now)
    state = str(h.get("state") or "unknown")
    if state != "connected":
        st = "down"
    elif market_open and (age is None or age > COLLECTOR_STALE_S):
        st = "stale"
    else:
        st = "ok"
    return {
        "status": st,
        "provider": h.get("provider"),
        "state": state,
        "is_demo": bool(h.get("is_demo")),
        "last_message_at": last.isoformat() if last else None,
        "last_message_age_s": age,
        "tracked": h.get("tracked"),
        "message": h.get("message"),
    }


async def trader_status(ctx: ActionContext, now: datetime) -> dict[str, Any]:
    h = await _redis_json(ctx, "trader:health")
    if h is None:
        return {"status": "missing", "message": "trader:health not in Redis (trader not running)"}
    upd = _parse_ts(h.get("updated_at"))
    age = _age_s(upd, now)
    halted = [a for a in h.get("accounts", []) if isinstance(a, dict) and a.get("halted")]
    return {
        "status": "ok" if age is not None and age <= TRADER_STALE_S else "stale",
        "updated_at": upd.isoformat() if upd else None,
        "age_s": age,
        "activations": len(h.get("activations", []) or []),
        "halted_accounts": [{"id": a.get("id"), "reason": a.get("halted")} for a in halted],
    }


async def worker_status(ctx: ActionContext, now: datetime) -> dict[str, Any]:
    raw = await ctx.redis_text("worker:heartbeat")
    ts = _parse_ts(raw)
    if ts is None:
        return {"status": "missing", "message": "no worker heartbeat in Redis"}
    age = _age_s(ts, now)
    ok = age is not None and age <= WORKER_STALE_S
    return {"status": "ok" if ok else "stale", "last_heartbeat": ts.isoformat(), "age_s": age}


async def broker_rows(ctx: ActionContext, now: datetime) -> list[dict[str, Any]]:
    if ctx.secret_box is None:
        return [
            {"broker": c, "status": "unknown", "message": "SECRETS_KEY not configured"}
            for c in sorted(SUPPORTED)
        ]
    db = ctx.session()
    svc = BrokerService(db, ctx.settings, ctx.secret_box)
    if ctx.user_id is not None:
        users = [ctx.user_id]
    else:
        q = select(BrokerAccount.user_id).where(BrokerAccount.is_active.is_(True)).distinct()
        users = [u for (u,) in (await db.execute(q)).all()]
    rows: list[dict[str, Any]] = []
    for code in sorted(SUPPORTED):
        found = False
        for uid in users:
            try:
                st = await svc.status(uid, code)
            except BrokerError as exc:
                rows.append({"broker": code, "status": "unknown", "message": str(exc)})
                found = True
                break
            if st.account_id is None:
                continue
            found = True
            mins = None
            if st.expires_at is not None:
                mins = int((st.expires_at - now).total_seconds() // 60)
            rows.append(
                {
                    "broker": code,
                    "account_id": st.account_id,
                    "configured": st.configured,
                    "status": st.status,
                    "expires_at": st.expires_at.isoformat() if st.expires_at else None,
                    "expires_in_min": mins,
                    "last_checked_at": st.last_checked_at.isoformat()
                    if st.last_checked_at
                    else None,
                }
            )
        if not found:
            rows.append({"broker": code, "configured": False, "status": "not_configured"})
    return rows


def _broker_line(rows: list[dict[str, Any]]) -> str:
    parts = []
    for r in rows:
        if r["status"] == "valid" and r.get("expires_at"):
            exp = ensure_utc(r["expires_at"]).astimezone(IST).strftime("%d %b %H:%M IST")
            parts.append(f"{r['broker']} valid until {exp}")
        else:
            parts.append(f"{r['broker']} {r['status'].replace('_', ' ')}")
    return ", ".join(parts)


# ----------------------------------------------------------------------------- green
@REGISTRY.register(
    "health_check",
    "State of every process in one answer: database, Redis, collector feed, paper trader, "
    "worker heartbeat and broker sessions.",
    "green",
)
async def health_check(ctx: ActionContext, _: NoArgs) -> dict[str, Any]:
    now = ctx.now()
    market_open = nse_calendar().is_open(now)
    out: dict[str, Any] = {"checked_at": now.isoformat(), "market_open": market_open}
    try:
        await ctx.session().execute(text("select 1"))
        out["db"] = {"status": "ok"}
    except Exception as exc:
        out["db"] = {"status": "error", "message": type(exc).__name__}
    try:
        await ctx.redis.ping()
        out["redis"] = {"status": "ok"}
        out["collector"] = await collector_status(ctx, now, market_open)
        out["trader"] = await trader_status(ctx, now)
        out["worker"] = await worker_status(ctx, now)
    except Exception as exc:
        out["redis"] = {"status": "error", "message": type(exc).__name__}
        for k in ("collector", "trader", "worker"):
            out.setdefault(k, {"status": "unknown", "message": "Redis unreachable"})
    try:
        out["brokers"] = await broker_rows(ctx, now)
    except Exception as exc:
        out["brokers"] = [{"broker": "*", "status": "unknown", "message": type(exc).__name__}]
    problems = [k for k in ("db", "redis", "worker") if out[k]["status"] != "ok"]
    # Feed and trader only matter while the exchange is open; outside it they are reported
    # but do not make the platform "degraded".
    if market_open:
        problems += [k for k in ("collector", "trader") if out[k]["status"] != "ok"]
    out["status"] = "ok" if not problems else "degraded"
    out["problems"] = problems
    detail = ", ".join(f"{k} {out[k]['status']}" for k in problems)
    session = "market open" if market_open else "market closed"
    out["summary"] = f"{out['status']} ({session})" + (f": {detail}" if detail else "")
    return out


@REGISTRY.register(
    "broker_sessions",
    "Daily broker session per broker: valid, expired, revoked, missing or not configured, "
    "with expiry time.",
    "green",
)
async def broker_sessions(ctx: ActionContext, _: NoArgs) -> dict[str, Any]:
    rows = await broker_rows(ctx, ctx.now())
    return {"brokers": rows, "summary": _broker_line(rows)}


class SymbolsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbols: list[str] = Field(
        default_factory=lambda: list(CHAIN_SYMBOLS), min_length=1, max_length=10
    )

    def cleaned(self) -> list[str]:
        import re

        out = []
        for s in self.symbols:
            u = s.strip().upper()
            if not re.match(SYMBOL_PATTERN, u):
                raise ActionError(f"bad symbol {s!r}")
            out.append(u)
        return out


@REGISTRY.register(
    "regime_summary",
    "Latest stored daily regime (trend, strength, volatility, structure, VIX) and today's "
    "intraday day type per symbol.",
    "green",
    SymbolsArgs,
)
async def regime_summary(ctx: ActionContext, args: SymbolsArgs) -> dict[str, Any]:
    db = ctx.session()
    today = ctx.now().astimezone(IST).date()
    rows: list[dict[str, Any]] = []
    for sym in args.cleaned():
        ins = await get_by_symbol(db, "NSE", sym)
        if ins is None:
            rows.append({"symbol": sym, "status": "unknown symbol"})
            continue
        d = await latest_daily(db, ins.instrument_id)
        i = await latest_intraday(db, ins.instrument_id, today)
        row: dict[str, Any] = {"symbol": sym, "instrument_id": ins.instrument_id}
        if d is None:
            row["status"] = "no daily regime stored"
        else:
            row["status"] = "ok"
            row["daily"] = {
                k: v
                for k, v in d.as_dict().items()
                if k not in ("daily_trend", "ema20", "ema50", "ema200")
            }
        row["intraday"] = (
            {"ts": i.ts.isoformat(), "day_type": i.day_type} if i is not None else None
        )
        rows.append(row)
    parts = []
    for r in rows:
        if r.get("daily"):
            dd = r["daily"]
            parts.append(
                f"{r['symbol']} {dd['trend']}/{dd['strength']} "
                f"vol {dd['volatility']} ({dd['date']})"
            )
        else:
            parts.append(f"{r['symbol']}: {r['status']}")
    return {"regimes": rows, "summary": "; ".join(parts)}


@REGISTRY.register(
    "pcr_now",
    "Put/call ratio by open interest from the newest stored option-chain snapshot (nearest "
    "expiry, last 24 h), compared with the owner's pcr_guard thresholds.",
    "green",
    SymbolsArgs,
)
async def pcr_now(ctx: ActionContext, args: SymbolsArgs) -> dict[str, Any]:
    db = ctx.session()
    now = ctx.now()
    lim = RiskLimits()
    rows: list[dict[str, Any]] = []
    for sym in args.cleaned():
        ins = await get_by_symbol(db, "NSE", sym)
        if ins is None:
            rows.append({"symbol": sym, "status": "unknown symbol", "pcr": None})
            continue
        oi = await latest_chain_oi(db, ins.instrument_id, now)
        if oi is None:
            rows.append(
                {
                    "symbol": sym,
                    "instrument_id": ins.instrument_id,
                    "status": "no option-chain snapshot in the last 24 h",
                    "pcr": None,
                }
            )
            continue
        prov = (
            await db.execute(
                select(DataProvider.code, DataProvider.is_demo)
                .join(OptionChainSnapshot, OptionChainSnapshot.provider_id == DataProvider.id)
                .where(
                    OptionChainSnapshot.underlying_instrument_id == ins.instrument_id,
                    OptionChainSnapshot.ts == oi.ts,
                    OptionChainSnapshot.expiry == oi.expiry,
                )
                .limit(1)
            )
        ).first()
        pcr = pcr_from_oi(oi.put_oi, oi.call_oi)
        age_min = int((now - oi.ts).total_seconds() // 60)
        if pcr is None:
            zone = "no call OI"
        elif pcr >= Decimal(str(lim.pcr_no_put_buy_at)):
            zone = "blocks PUT buys"
        elif pcr <= Decimal(str(lim.pcr_no_call_buy_at)):
            zone = "blocks CALL buys"
        else:
            zone = "neutral"
        rows.append(
            {
                "symbol": sym,
                "instrument_id": ins.instrument_id,
                "status": "ok",
                "pcr": pcr,
                "put_oi": oi.put_oi,
                "call_oi": oi.call_oi,
                "expiry": oi.expiry.date().isoformat(),
                "snapshot_ts": oi.ts.isoformat(),
                "age_min": age_min,
                "freshness": "fresh" if age_min <= lim.pcr_max_age_minutes else "stale",
                "source": prov[0] if prov else None,
                "is_demo": bool(prov[1]) if prov else None,
                "rule_zone": zone,
            }
        )
    thresholds = {
        "no_put_buy_at": lim.pcr_no_put_buy_at,
        "no_call_buy_at": lim.pcr_no_call_buy_at,
        "max_age_minutes": lim.pcr_max_age_minutes,
    }
    parts = []
    for r in rows:
        if r["pcr"] is None:
            parts.append(f"{r['symbol']}: {r['status']}")
        else:
            demo = " DEMO" if r.get("is_demo") else ""
            parts.append(f"{r['symbol']} {r['pcr']:.2f} ({r['freshness']}{demo}, {r['rule_zone']})")
    return {"pcr": rows, "thresholds": thresholds, "summary": "; ".join(parts)}


async def _accounts(ctx: ActionContext) -> list[PaperAccount]:
    q = select(PaperAccount).where(PaperAccount.is_active.is_(True)).order_by(PaperAccount.id)
    if ctx.user_id is not None:
        q = q.where(PaperAccount.user_id == ctx.user_id)
    return list((await ctx.session().execute(q)).scalars().all())


async def _symbols(ctx: ActionContext, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    rows = await ctx.session().execute(
        select(Instrument.id, Instrument.symbol).where(Instrument.id.in_(ids))
    )
    return {i: s for i, s in rows.all()}


@REGISTRY.register(
    "paper_status",
    "Paper accounts: cash, open positions, today's realised and open P&L, running "
    "strategies, loss-limit halts and kill switches.",
    "green",
)
async def paper_status(ctx: ActionContext, _: NoArgs) -> dict[str, Any]:
    db = ctx.session()
    now = ctx.now()
    day_start, _end = ist_day_bounds(now)
    ks = KillSwitch(ctx.redis)
    accounts = await _accounts(ctx)
    out_accounts: list[dict[str, Any]] = []
    total_open = 0
    total_running = 0
    for a in accounts:
        pos = list(
            (
                await db.execute(
                    select(PaperPosition).where(
                        PaperPosition.paper_account_id == a.id,
                        PaperPosition.closed_at.is_(None),
                        PaperPosition.quantity != 0,
                    )
                )
            )
            .scalars()
            .all()
        )
        realized_today = Decimal(
            (
                await db.execute(
                    select(func.coalesce(func.sum(PaperTrade.net_pnl), 0)).where(
                        PaperTrade.paper_account_id == a.id, PaperTrade.exit_at >= day_start
                    )
                )
            ).scalar_one()
        )
        trades_today = (
            await db.execute(
                select(func.count(PaperTrade.id)).where(
                    PaperTrade.paper_account_id == a.id, PaperTrade.exit_at >= day_start
                )
            )
        ).scalar_one()
        acts = list(
            (
                await db.execute(
                    select(StrategyActivation).where(
                        StrategyActivation.paper_account_id == a.id,
                        StrategyActivation.status != ActivationStatus.STOPPED,
                    )
                )
            )
            .scalars()
            .all()
        )
        sym = await _symbols(ctx, {p.instrument_id for p in pos} | {x.instrument_id for x in acts})
        unreal = sum((p.unrealized_pnl for p in pos), Decimal("0"))
        halt = await ctx.redis_text(f"trader:halt:{a.id}")
        kills = await ks.any_active(a.id, None)
        total_open += len(pos)
        total_running += sum(1 for x in acts if x.status == ActivationStatus.ACTIVE)
        out_accounts.append(
            {
                "id": a.id,
                "name": a.name,
                "currency": a.currency,
                "initial_capital": a.initial_capital,
                "cash": a.cash,
                "realized_today": realized_today,
                "trades_closed_today": int(trades_today),
                "unrealized_open": unreal,
                "day_pnl": realized_today + unreal,
                "open_positions": [
                    {
                        "id": p.id,
                        "symbol": sym.get(p.instrument_id),
                        "instrument_id": p.instrument_id,
                        "quantity": p.quantity,
                        "avg_price": p.avg_price,
                        "last_price": p.last_price,
                        "unrealized_pnl": p.unrealized_pnl,
                        "activation_id": p.activation_id,
                    }
                    for p in pos
                ],
                "activations": [
                    {
                        "id": x.id,
                        "status": x.status,
                        "version_id": x.version_id,
                        "symbol": sym.get(x.instrument_id),
                    }
                    for x in acts
                ],
                "halted": halt,
                "kill_switches": kills,
            }
        )
    if not accounts:
        summary = "no active paper accounts"
    else:
        day = sum((a["day_pnl"] for a in out_accounts), Decimal("0"))
        summary = (
            f"{len(accounts)} account(s), {total_running} running strategies, "
            f"{total_open} open position(s), day P&L {day:.2f} (realised + open, paper)"
        )
        if any(a["halted"] for a in out_accounts):
            summary += ", HALTED account(s)"
    return {"accounts": out_accounts, "as_of": now.isoformat(), "summary": summary}


@REGISTRY.register(
    "todays_events",
    "Market events stored in the events calendar for today (IST): RBI, Fed, budget, expiry, "
    "results; with impact and whether they block trading.",
    "green",
)
async def todays_events(ctx: ActionContext, _: NoArgs) -> dict[str, Any]:
    start, end = ist_day_bounds(ctx.now())
    rows = (
        (
            await ctx.session().execute(
                select(Event)
                .where(Event.starts_at >= start, Event.starts_at < end)
                .order_by(Event.starts_at)
            )
        )
        .scalars()
        .all()
    )
    events = [
        {
            "id": e.id,
            "type": e.event_type,
            "title": e.title,
            "impact": e.impact,
            "blocks_trading": e.blocks_trading,
            "starts_at": e.starts_at.isoformat(),
            "ends_at": e.ends_at.isoformat() if e.ends_at else None,
            "source": e.source,
        }
        for e in rows
    ]
    if not events:
        summary = "no events stored for today"
    else:
        summary = f"{len(events)} event(s): " + ", ".join(str(e["title"]) for e in events[:5])
    return {"date": start.astimezone(IST).date().isoformat(), "events": events, "summary": summary}


class RecentAlertsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hours: int = Field(default=24, ge=1, le=168)
    limit: int = Field(default=50, ge=1, le=200)
    unacknowledged_only: bool = False


@REGISTRY.register(
    "recent_alerts",
    "Alerts stored in the last N hours (newest first), with severity and acknowledgement.",
    "green",
    RecentAlertsArgs,
)
async def recent_alerts(ctx: ActionContext, args: RecentAlertsArgs) -> dict[str, Any]:
    since = ctx.now() - timedelta(hours=args.hours)
    q = select(Alert).where(Alert.ts >= since).order_by(Alert.ts.desc()).limit(args.limit)
    if args.unacknowledged_only:
        q = q.where(Alert.acknowledged_at.is_(None))
    rows = (await ctx.session().execute(q)).scalars().all()
    alerts = [
        {
            "id": a.id,
            "ts": a.ts.isoformat(),
            "kind": a.kind,
            "severity": a.severity,
            "title": a.title,
            "acknowledged": a.acknowledged_at is not None,
        }
        for a in rows
    ]
    crit = sum(1 for a in alerts if a["severity"] == "critical")
    summary = (
        f"no alerts in the last {args.hours} h"
        if not alerts
        else f"{len(alerts)} alert(s) in the last {args.hours} h, {crit} critical"
    )
    return {"alerts": alerts, "summary": summary}


# ----------------------------------------------------------------------------- yellow
class KillArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: str = Field(default="global", pattern=r"^(global|account:\d+|strategy:\d+)$")
    reason: str = Field(default="protocol: clean slate", min_length=3, max_length=200)
    flatten: bool = False


@REGISTRY.register(
    "kill_switch_on",
    "Engage the kill switch: every new entry is blocked at once (plan §2.3: turning it ON is "
    "always immediate; turning it off is red and stays with the owner on the Risk page).",
    "yellow",
    KillArgs,
)
async def kill_switch_on(ctx: ActionContext, args: KillArgs) -> dict[str, Any]:
    ks = KillSwitch(ctx.redis)
    existing = await ks.status(args.scope)
    if existing is not None:
        return {
            "scope": args.scope,
            "active": True,
            "already_active": True,
            "detail": existing,
            "summary": f"kill switch {args.scope} already ON ({existing.get('reason')})",
        }
    by = f"protocol (user {ctx.user_id})" if ctx.user_id is not None else "protocol"
    # Redis first: the switch is on even if the DB write below fails.
    ev = await ks.activate(args.scope, args.reason + (" [flatten]" if args.flatten else ""), by)
    kind, _, sid = args.scope.partition(":")
    db = ctx.session()
    db.add(
        KillSwitchEvent(
            scope=KillSwitchScope(kind),
            scope_id=int(sid) if sid else None,
            action=KillSwitchAction.ACTIVATE,
            reason=args.reason,
            triggered_by=ctx.user_id,
            actor_type=ctx.actor,
            positions_flattened=args.flatten,
            ts=ctx.now(),
        )
    )
    write_audit(
        db,
        user_id=ctx.user_id,
        action="kill_switch.activate",
        entity_type="kill_switch",
        entity_id=args.scope,
        reason=args.reason,
        after=ev,
        actor=ctx.actor,
    )
    await db.flush()
    await ctx.notifier.send(
        f"KILL SWITCH ON ({args.scope}) by protocol: {args.reason}", level="critical"
    )
    return {
        "scope": args.scope,
        "active": True,
        "already_active": False,
        "detail": await ks.status(args.scope),
        "summary": f"kill switch {args.scope} ON",
    }


class StopArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(default="protocol: shutdown", min_length=3, max_length=200)
    flatten: bool = True


@REGISTRY.register(
    "stop_paper_strategies",
    "Stop every running paper strategy (same path as the Stop button). With flatten, the "
    "paper trader squares off their positions on its next refresh (about 10 s).",
    "yellow",
    StopArgs,
)
async def stop_paper_strategies(ctx: ActionContext, args: StopArgs) -> dict[str, Any]:
    db = ctx.session()
    acts = await running_paper_activations(db, ctx.user_id)
    stopped = []
    for a in acts:
        if await stop_activation(
            db, a, reason=args.reason, flatten=args.flatten, user_id=ctx.user_id, actor=ctx.actor
        ):
            stopped.append({"activation_id": a.id, "paper_account_id": a.paper_account_id})
    await db.flush()
    summary = (
        "no running paper strategies"
        if not stopped
        else f"{len(stopped)} paper strategy activation(s) stopped"
        + (" (flatten requested)" if args.flatten else "")
    )
    return {"stopped": stopped, "flatten": args.flatten, "summary": summary}


class CloseArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(default="protocol: close positions", min_length=3, max_length=200)


@REGISTRY.register(
    "close_paper_positions",
    "Request a square-off of every open paper position. Positions are closed by the paper "
    "trader through the execution simulator (the session square-off path): their strategy "
    "is stopped with flatten. Reports what was requested; it never reports a fill itself.",
    "yellow",
    CloseArgs,
)
async def close_paper_positions(ctx: ActionContext, args: CloseArgs) -> dict[str, Any]:
    db = ctx.session()
    now = ctx.now()
    ids = [a.id for a in await _accounts(ctx)]
    pos = (
        list(
            (
                await db.execute(
                    select(PaperPosition).where(
                        PaperPosition.paper_account_id.in_(ids),
                        PaperPosition.closed_at.is_(None),
                        PaperPosition.quantity != 0,
                    )
                )
            )
            .scalars()
            .all()
        )
        if ids
        else []
    )
    if not pos:
        return {"positions": [], "summary": "no open paper positions"}
    trader = await trader_status(ctx, now)
    if trader["status"] != "ok":
        raise ActionError(
            f"paper trader is {trader['status']}: {len(pos)} open position(s) cannot be "
            "squared off now and stay open"
        )
    sym = await _symbols(ctx, {p.instrument_id for p in pos})
    rows: list[dict[str, Any]] = []
    for p in pos:
        row: dict[str, Any] = {
            "position_id": p.id,
            "symbol": sym.get(p.instrument_id),
            "quantity": p.quantity,
            "activation_id": p.activation_id,
        }
        act = await db.get(StrategyActivation, p.activation_id) if p.activation_id else None
        if act is None:
            row["outcome"] = "not_closable"
            row["note"] = "no strategy owns this position; the trader cannot square it off"
        elif act.status != ActivationStatus.STOPPED:
            await stop_activation(
                db, act, reason=args.reason, flatten=True, user_id=ctx.user_id, actor=ctx.actor
            )
            row["outcome"] = "flatten_requested"
        else:
            row["outcome"] = "flatten_pending"
            row["note"] = "strategy already stopped; the trader squares it off while it holds it"
        rows.append(row)
    await db.flush()
    req = sum(1 for r in rows if r["outcome"] != "not_closable")
    bad = len(rows) - req
    summary = f"square-off requested for {req} position(s); fills are reported by the trader"
    if bad:
        summary += f"; {bad} position(s) cannot be closed (no owning strategy)"
    return {"positions": rows, "summary": summary}
