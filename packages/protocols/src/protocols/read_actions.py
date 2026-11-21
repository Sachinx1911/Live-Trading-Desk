"""Green read actions added for the Stage 4 tool catalogue (docs/tool-server.md).

They are registered in the same `REGISTRY` as the Stage 3 protocol actions, so protocols can
use them too and there is one list of what the platform can do. Every one is read only: no
order, no write, no provider call (only stored rows and Redis keys the owning process wrote).

Every result carries `source`, `freshness` and `is_demo` (CLAUDE.md rule 5). `freshness` uses
the values of `core.models.Freshness` plus `none` for answers that have no market source
(health, protocol runs, owner rules) or when nothing is stored. Missing data is reported as
missing with a reason; nothing is filled in or guessed.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from core.calendar import nse_calendar
from core.db.models import (
    BacktestJob,
    BacktestResult,
    DailyReport,
    DataProvider,
    HistoricalCandle,
    PaperPosition,
    PaperTrade,
    Protocol,
    ProtocolRun,
)
from core.db.models import OptionChainSnapshot as SnapRow
from core.models import Freshness, Instrument, Timeframe
from core.time import IST, ensure_utc
from market_data.breadth.repo import latest_breadth, list_breadth
from market_data.breadth.universe import NIFTY50_AS_OF, UNIVERSES
from market_data.news.repo import item_dict, list_news, matcher_for
from market_data.oi_change import (
    compare_chains,
    expiries_on_day,
    snapshot_pair,
)
from market_data.oi_change import ist_day_bounds as ist_date_bounds
from market_data.oi_change import pcr as chain_pcr
from market_data.repo._lookup import provider_id
from market_data.repo.candles import fetch_candles
from market_data.repo.chains import oi_totals
from market_data.repo.instruments import get_by_symbol
from market_data.repo.quotes import get_cached_quotes
from market_data.scanner.filters import ScanQuery, ScanQueryError, apply_query
from market_data.scanner.presets import PRESETS
from market_data.scanner.repo import latest_snapshot as latest_scan_snapshot
from market_data.strike_series import derive_points
from protocols.actions import (
    REGISTRY,
    SYMBOL_PATTERN,
    _accounts,
    _symbols,
    collector_status,
    ist_day_bounds,
    trader_status,
)
from protocols.context import ActionContext
from protocols.registry import ActionError, NoArgs
from risk.limits import RiskLimits
from risk.owner_rules import OWNER_RULES

NONE = "none"  # no market source behind the answer, or nothing stored
FRESHNESS_VALUES: tuple[str, ...] = (*(f.value for f in Freshness), NONE)
# Worst-first order used when one answer covers several rows (demo always wins: rule 5).
_FRESH_RANK = {
    Freshness.LIVE.value: 0,
    Freshness.DELAYED.value: 1,
    Freshness.STALE.value: 2,
    Freshness.HISTORICAL.value: 3,
    Freshness.DISCONNECTED.value: 4,
    NONE: 5,
}
CHAIN_DELAYED_S = 600  # a chain snapshot younger than this, in session, is "delayed"
EXCHANGE_PATTERN = r"^[A-Z]{2,8}$"
TRADING_RULES_DOC = "docs/trading-rules.md"


# ----------------------------------------------------------------------------- helpers
def provenance(source: str, freshness: str, is_demo: bool) -> dict[str, Any]:
    if freshness not in FRESHNESS_VALUES:
        raise ValueError(f"bad freshness {freshness!r}")
    return {"source": source, "freshness": freshness, "is_demo": bool(is_demo)}


def combine_freshness(values: Iterable[str]) -> str:
    # Rows with nothing behind them ("none") do not hide what the other rows are.
    vals = [v for v in values if v != NONE]
    if not vals:
        return NONE
    if Freshness.DEMO.value in vals:
        return Freshness.DEMO.value
    return max(vals, key=lambda v: _FRESH_RANK.get(v, 5))


async def provider_is_demo(ctx: ActionContext, code: str) -> bool:
    row = (
        await ctx.session().execute(select(DataProvider.is_demo).where(DataProvider.code == code))
    ).scalar_one_or_none()
    return bool(row) if row is not None else code == "fake"


async def active_provider(ctx: ActionContext) -> tuple[str, bool]:
    code = ctx.settings.default_market_data_provider
    return code, await provider_is_demo(ctx, code)


async def _provider_db_id(ctx: ActionContext, code: str) -> int:
    try:
        return await provider_id(ctx.session(), code)
    except LookupError as exc:
        raise ActionError(str(exc)) from exc


def _clean(symbol: str) -> str:
    import re

    u = symbol.strip().upper()
    if not re.match(SYMBOL_PATTERN, u):
        raise ActionError(f"bad symbol {symbol!r}")
    return u


async def _instrument(ctx: ActionContext, symbol: str, exchange: str) -> Instrument:
    sym = _clean(symbol)
    ins = await get_by_symbol(ctx.session(), exchange, sym)
    if ins is None:
        raise ActionError(f"unknown symbol {sym!r} on {exchange}")
    return ins


def _f(v: Any) -> float | None:
    return None if v is None else float(v)


def _market_open(ctx: ActionContext, now: datetime) -> bool:
    return nse_calendar().is_open(now)


class _Sym(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exchange: str = Field(default="NSE", pattern=EXCHANGE_PATTERN)


# ----------------------------------------------------------------------------- quote
class QuoteArgs(_Sym):
    symbols: list[str] = Field(min_length=1, max_length=20)


async def _last_close(
    ctx: ActionContext, instrument_id: int, provider: str
) -> dict[str, Any] | None:
    """Newest stored 1m or daily bar of the active provider: shown as historical, never as a
    quote."""
    q = (
        select(HistoricalCandle, DataProvider.is_demo)
        .join(DataProvider, DataProvider.id == HistoricalCandle.provider_id)
        .where(
            HistoricalCandle.instrument_id == instrument_id,
            DataProvider.code == provider,
            HistoricalCandle.timeframe.in_([Timeframe.M1, Timeframe.D1]),
        )
        .order_by(HistoricalCandle.ts.desc())
        .limit(1)
    )
    row = (await ctx.session().execute(q)).first()
    if row is None:
        return None
    c, demo = row
    return {
        "close": c.close,
        "bar_ts": c.ts.isoformat(),
        "timeframe": str(c.timeframe.value if hasattr(c.timeframe, "value") else c.timeframe),
        "source": provider,
        "freshness": Freshness.DEMO.value if demo else Freshness.HISTORICAL.value,
        "is_demo": bool(demo),
    }


@REGISTRY.register(
    "quote",
    "Latest quote per symbol from the collector's Redis cache, with its own freshness "
    "(live < 2 s, delayed < 30 s, else stale). A symbol with no cached quote is reported "
    "disconnected with the reason and the last stored close labelled historical.",
    "green",
    QuoteArgs,
)
async def quote(ctx: ActionContext, args: QuoteArgs) -> dict[str, Any]:
    now = ctx.now()
    provider, provider_demo = await active_provider(ctx)
    market_open = _market_open(ctx, now)
    collector = await collector_status(ctx, now, market_open)
    resolved: list[tuple[str, Instrument | None]] = []
    for s in args.symbols:
        sym = _clean(s)
        resolved.append((sym, await get_by_symbol(ctx.session(), args.exchange, sym)))
    ids = [i.instrument_id for _, i in resolved if i is not None]
    cached = await get_cached_quotes(ctx.redis, ids, now)
    why: list[str] = []
    if not market_open:
        why.append("NSE market closed")
    if collector["status"] != "ok":
        why.append(
            f"collector {collector['status']}: {collector.get('message') or collector.get('state')}"
        )
    reason = "; ".join(why) or "collector has not cached this instrument"
    rows: list[dict[str, Any]] = []
    for sym, ins in resolved:
        if ins is None:
            rows.append(
                {
                    "symbol": sym,
                    "status": "unknown symbol",
                    "ltp": None,
                    **provenance(provider, NONE, provider_demo),
                }
            )
            continue
        q = cached.get(ins.instrument_id)
        if q is not None:
            fresh = Freshness.DEMO if q.is_demo else q.freshness
            rows.append(
                {
                    "symbol": sym,
                    "instrument_id": ins.instrument_id,
                    "status": "ok",
                    "ltp": q.ltp,
                    "bid": q.bid,
                    "ask": q.ask,
                    "volume": q.volume,
                    "oi": q.oi,
                    "prev_close": q.prev_close,
                    "change_pct": (
                        ((q.ltp - q.prev_close) / q.prev_close * 100).quantize(Decimal("0.01"))
                        if q.prev_close
                        else None
                    ),
                    "ts": q.ts.isoformat(),
                    "age_s": round((now - ensure_utc(q.ts)).total_seconds(), 1),
                    **provenance(q.provider_id, fresh.value, q.is_demo),
                }
            )
            continue
        rows.append(
            {
                "symbol": sym,
                "instrument_id": ins.instrument_id,
                "status": "no live quote",
                "ltp": None,
                "reason": reason,
                "last_close": await _last_close(ctx, ins.instrument_id, provider),
                **provenance(provider, Freshness.DISCONNECTED.value, provider_demo),
            }
        )
    fresh_all = combine_freshness(r["freshness"] for r in rows)
    demo_all = any(r["is_demo"] for r in rows)
    sources = sorted({str(r["source"]) for r in rows})
    parts = []
    for r in rows:
        if r["ltp"] is not None:
            at = ensure_utc(r["ts"]).astimezone(IST).strftime("%d %b %H:%M:%S IST")
            parts.append(f"{r['symbol']} {r['ltp']} ({r['freshness']}, quote time {at})")
        else:
            parts.append(f"{r['symbol']}: {r['status']}")
    return {
        "quotes": rows,
        "market_open": market_open,
        "collector": {
            k: collector.get(k) for k in ("status", "state", "provider", "last_message_at")
        },
        "as_of": now.isoformat(),
        "summary": "; ".join(parts),
        **provenance(",".join(sources), fresh_all, demo_all),
    }


# ----------------------------------------------------------------------------- candles
class CandlesArgs(_Sym):
    symbol: str = Field(min_length=1, max_length=32)
    timeframe: Timeframe = Timeframe.M5
    limit: int = Field(default=100, ge=1, le=500)


@REGISTRY.register(
    "candles",
    "Last N stored candles of one symbol and timeframe, active market-data provider only "
    "(series are never mixed across providers). Stored bars are historical (or demo).",
    "green",
    CandlesArgs,
)
async def candles(ctx: ActionContext, args: CandlesArgs) -> dict[str, Any]:
    if args.timeframe in (Timeframe.TICK, Timeframe.S1):
        raise ActionError("tick and 1s data are not served as candles")
    ins = await _instrument(ctx, args.symbol, args.exchange)
    provider, provider_demo = await active_provider(ctx)
    now = ctx.now()
    dur = args.timeframe.duration
    # Intraday bars only exist in session hours: look back far enough to find N of them.
    span = dur * args.limit * 4 + timedelta(days=7) if dur else timedelta(days=3650)
    rows = await fetch_candles(
        ctx.session(),
        ins.instrument_id,
        args.timeframe,
        now - span,
        now + timedelta(minutes=1),
        provider,
    )
    rows = rows[-args.limit :]
    bars = [
        {
            "ts": c.ts.isoformat(),
            "open": c.open,
            "high": c.high,
            "low": c.low,
            "close": c.close,
            "volume": c.volume,
            "oi": c.oi,
        }
        for c in rows
    ]
    if not rows:
        return {
            "symbol": ins.symbol,
            "instrument_id": ins.instrument_id,
            "timeframe": args.timeframe.value,
            "candles": [],
            "status": "no_data",
            "summary": f"no {args.timeframe.value} candles stored for {ins.symbol} from {provider}",
            **provenance(provider, NONE, provider_demo),
        }
    demo = any(c.is_demo for c in rows)
    last = rows[-1]
    return {
        "symbol": ins.symbol,
        "instrument_id": ins.instrument_id,
        "timeframe": args.timeframe.value,
        "candles": bars,
        "status": "ok",
        "last_bar_ts": last.ts.isoformat(),
        "last_bar_age_min": int((now - last.ts).total_seconds() // 60),
        "summary": (
            f"{len(rows)} {args.timeframe.value} candles of {ins.symbol}, last close {last.close} "
            f"at {last.ts.astimezone(IST).strftime('%d %b %H:%M IST')}"
        ),
        **provenance(provider, Freshness.DEMO.value if demo else Freshness.HISTORICAL.value, demo),
    }


# ----------------------------------------------------------------------------- chains
class ChainArgs(_Sym):
    underlying: str = Field(default="NIFTY", min_length=1, max_length=32)
    expiry: date | None = Field(default=None, description="IST expiry date; default nearest")
    strikes_around_atm: int = Field(default=10, ge=1, le=60)


async def _snapshot(
    ctx: ActionContext,
    underlying_id: int,
    pid: int,
    expiry: date | None,
    at: datetime | None = None,
) -> SnapRow | None:
    q = select(SnapRow).where(
        SnapRow.underlying_instrument_id == underlying_id,
        SnapRow.provider_id == pid,
        SnapRow.row_count > 0,
    )
    if expiry is not None:
        lo, hi = ist_date_bounds(expiry)
        q = q.where(SnapRow.expiry >= lo, SnapRow.expiry < hi)
    if at is not None:
        q = q.where(SnapRow.ts <= ensure_utc(at))
    q = q.order_by(SnapRow.ts.desc(), SnapRow.expiry.asc()).limit(1)
    return (await ctx.session().execute(q)).scalar_one_or_none()


def _chain_freshness(now: datetime, ts: datetime, demo: bool, at: datetime | None) -> str:
    if demo:
        return Freshness.DEMO.value
    if at is not None or not nse_calendar().is_open(now):
        return Freshness.HISTORICAL.value
    age = (now - ensure_utc(ts)).total_seconds()
    return Freshness.DELAYED.value if age < CHAIN_DELAYED_S else Freshness.STALE.value


def _strike_window(
    strikes: list[Decimal], spot: Decimal | None, n: int
) -> tuple[list[Decimal], Decimal | None]:
    if not strikes or spot is None:
        return strikes, None
    atm = min(strikes, key=lambda s: (abs(s - spot), s))
    i = strikes.index(atm)
    return strikes[max(0, i - n) : i + n + 1], atm


def _dec(v: Any) -> Decimal | None:
    if v is None or isinstance(v, bool):
        return None
    try:
        return Decimal(str(v))
    except ArithmeticError:
        return None


async def _chain_context(
    ctx: ActionContext, args: ChainArgs, at: datetime | None = None
) -> tuple[Instrument, str, bool, SnapRow | None]:
    ins = await _instrument(ctx, args.underlying, args.exchange)
    provider, demo = await active_provider(ctx)
    pid = await _provider_db_id(ctx, provider)
    snap = await _snapshot(ctx, ins.instrument_id, pid, args.expiry, at)
    return ins, provider, demo, snap


def _no_chain(ins: Instrument, provider: str, demo: bool, expiry: date | None) -> dict[str, Any]:
    what = f" expiring {expiry.isoformat()}" if expiry else ""
    return {
        "underlying": ins.symbol,
        "status": "no_data",
        "rows": [],
        "summary": f"no option-chain snapshot stored for {ins.symbol}{what} from {provider}",
        **provenance(provider, NONE, demo),
    }


@REGISTRY.register(
    "option_chain",
    "Newest stored option-chain snapshot (collector, every ~3 min) for an underlying and "
    "expiry, trimmed to ATM +/- N strikes: LTP, OI, OI change, volume, IV per side, PCR.",
    "green",
    ChainArgs,
)
async def option_chain(ctx: ActionContext, args: ChainArgs) -> dict[str, Any]:
    ins, provider, demo, snap = await _chain_context(ctx, args)
    if snap is None:
        return _no_chain(ins, provider, demo, args.expiry)
    now = ctx.now()
    spot = snap.underlying_price
    strikes = sorted({d for r in snap.rows if (d := _dec(r.get("strike"))) is not None})
    window, atm = _strike_window(strikes, spot, args.strikes_around_atm)
    keep = set(window)
    rows = [
        {
            "strike": _dec(r.get("strike")),
            "option_type": r.get("option_type"),
            "ltp": r.get("ltp"),
            "bid": r.get("bid"),
            "ask": r.get("ask"),
            "oi": r.get("oi"),
            "oi_change": r.get("oi_change"),
            "volume": r.get("volume"),
            "iv": r.get("iv"),
        }
        for r in snap.rows
        if _dec(r.get("strike")) in keep
    ]
    rows.sort(key=lambda r: (r["strike"], str(r["option_type"])))
    put, call = oi_totals(snap.rows)
    pcr = chain_pcr(snap.rows)
    fresh = _chain_freshness(now, snap.ts, demo, None)
    exp = ensure_utc(snap.expiry).astimezone(IST).date()
    return {
        "underlying": ins.symbol,
        "underlying_instrument_id": ins.instrument_id,
        "status": "ok",
        "expiry": exp.isoformat(),
        "snapshot_ts": snap.ts.isoformat(),
        "age_min": int((now - snap.ts).total_seconds() // 60),
        "underlying_price": spot,
        "atm_strike": atm,
        "pcr": pcr,
        "put_oi_total": put,
        "call_oi_total": call,
        "strikes_total": len(strikes),
        "rows": rows,
        "summary": (
            f"{ins.symbol} {exp.isoformat()} chain at "
            f"{snap.ts.astimezone(IST).strftime('%d %b %H:%M IST')}: spot {spot}, ATM {atm}, "
            f"PCR {pcr} ({fresh})"
        ),
        **provenance(provider, fresh, demo),
    }


class GreeksArgs(ChainArgs):
    strikes_around_atm: int = Field(default=5, ge=1, le=40)
    at: datetime | None = Field(
        default=None, description="Greeks as of this moment (newest snapshot at or before it)"
    )


@REGISTRY.register(
    "greeks",
    "IV, delta, gamma, theta and vega per strike and side from a stored option-chain "
    "snapshot (newest, or the newest at or before `at`), exactly as the provider sent them; "
    "null where the provider sent none (no local model).",
    "green",
    GreeksArgs,
)
async def greeks(ctx: ActionContext, args: GreeksArgs) -> dict[str, Any]:
    ins, provider, demo, snap = await _chain_context(ctx, args, args.at)
    if snap is None:
        return _no_chain(ins, provider, demo, args.expiry)
    now = ctx.now()
    points = derive_points(snap.rows, None)
    strikes = sorted({p.strike for p in points})
    window, atm = _strike_window(strikes, snap.underlying_price, args.strikes_around_atm)
    keep = set(window)
    by_strike: dict[Decimal, dict[str, Any]] = {}
    with_any = 0
    for p in points:
        if p.strike not in keep:
            continue
        g = {
            "ltp": p.ltp,
            "iv": p.iv,
            "delta": p.delta,
            "gamma": p.gamma,
            "theta": p.theta,
            "vega": p.vega,
        }
        if any(g[k] is not None for k in ("iv", "delta", "gamma", "theta", "vega")):
            with_any += 1
        by_strike.setdefault(p.strike, {"strike": p.strike, "CE": None, "PE": None})[
            p.option_type
        ] = g
    rows = [by_strike[s] for s in sorted(by_strike)]
    fresh = _chain_freshness(now, snap.ts, demo, args.at)
    exp = ensure_utc(snap.expiry).astimezone(IST).date()
    note = None if with_any else "the provider sent no Greeks in this snapshot"
    return {
        "underlying": ins.symbol,
        "status": "ok" if with_any else "no_greeks",
        "expiry": exp.isoformat(),
        "snapshot_ts": snap.ts.isoformat(),
        "underlying_price": snap.underlying_price,
        "atm_strike": atm,
        "rows": rows,
        "note": note,
        "summary": (
            f"{ins.symbol} {exp.isoformat()} Greeks at "
            f"{snap.ts.astimezone(IST).strftime('%d %b %H:%M IST')}, ATM {atm}"
            + (f"; {note}" if note else "")
        ),
        **provenance(provider, fresh, demo),
    }


class OiChangeArgs(_Sym):
    underlying: str = Field(default="NIFTY", min_length=1, max_length=32)
    expiry: date | None = Field(default=None, description="IST expiry; default nearest that day")
    day: date | None = Field(
        default=None, description="IST trading day; default the day of the newest snapshot"
    )
    start: str = Field(default="09:15", pattern=r"^\d{2}:\d{2}$")
    end: str = Field(default="15:30", pattern=r"^\d{2}:\d{2}$")
    strikes_around_atm: int = Field(default=10, ge=1, le=60)


@REGISTRY.register(
    "oi_change",
    "Per-strike call/put OI change between two times of one trading day (first stored "
    "snapshot at or after `start`, last at or before `end`, IST), with totals, PCR and spot "
    "at both ends. Uses the snapshots actually stored; nothing is interpolated.",
    "green",
    OiChangeArgs,
)
async def oi_change(ctx: ActionContext, args: OiChangeArgs) -> dict[str, Any]:
    ins = await _instrument(ctx, args.underlying, args.exchange)
    provider, demo = await active_provider(ctx)
    pid = await _provider_db_id(ctx, provider)
    now = ctx.now()
    try:
        t_start, t_end = time.fromisoformat(args.start), time.fromisoformat(args.end)
    except ValueError as exc:
        raise ActionError(f"bad time: {exc}") from exc
    day = args.day
    if day is None:
        newest = await _snapshot(ctx, ins.instrument_id, pid, None)
        if newest is None:
            return _no_chain(ins, provider, demo, args.expiry)
        day = ensure_utc(newest.ts).astimezone(IST).date()
    expiry = args.expiry
    if expiry is None:
        options = [
            e for e in await expiries_on_day(ctx.session(), ins.instrument_id, pid, day) if e >= day
        ]
        if not options:
            return {**_no_chain(ins, provider, demo, None), "day": day.isoformat()}
        expiry = options[0]
    t_from = ensure_utc(datetime.combine(day, t_start, tzinfo=IST))
    t_to = ensure_utc(datetime.combine(day, t_end, tzinfo=IST))
    if t_to <= t_from:
        raise ActionError("end must be after start")
    pair = await snapshot_pair(
        ctx.session(), ins.instrument_id, expiry, pid, t_from, min(t_to, now)
    )
    if pair is None:
        return {
            **_no_chain(ins, provider, demo, expiry),
            "day": day.isoformat(),
            "summary": f"no snapshot of {ins.symbol} {expiry.isoformat()} stored on {day} "
            f"between {args.start} and {args.end} IST",
        }
    a, b = pair.start, pair.end
    changes = compare_chains(a.rows, b.rows)
    strikes = [c.strike for c in changes]
    window, atm = _strike_window(strikes, b.underlying_price, args.strikes_around_atm)
    keep = set(window)
    if demo:
        fresh = Freshness.DEMO.value
    elif day != now.astimezone(IST).date() or not nse_calendar().is_open(now):
        fresh = Freshness.HISTORICAL.value
    else:
        fresh = _chain_freshness(now, b.ts, False, None)
    call_total = sum(c.call_change or 0 for c in changes)
    put_total = sum(c.put_change or 0 for c in changes)
    return {
        "underlying": ins.symbol,
        "status": "ok",
        "expiry": expiry.isoformat(),
        "day": day.isoformat(),
        "requested_from": t_from.isoformat(),
        "requested_to": t_to.isoformat(),
        "from_ts": a.ts.isoformat(),
        "to_ts": b.ts.isoformat(),
        "spot_from": a.underlying_price,
        "spot_to": b.underlying_price,
        "pcr_from": chain_pcr(a.rows),
        "pcr_to": chain_pcr(b.rows),
        "call_oi_change_total": call_total,
        "put_oi_change_total": put_total,
        "atm_strike": atm,
        "strikes": [
            {
                "strike": c.strike,
                "call_oi_from": c.call_oi_from,
                "call_oi_to": c.call_oi_to,
                "call_change": c.call_change,
                "put_oi_from": c.put_oi_from,
                "put_oi_to": c.put_oi_to,
                "put_change": c.put_change,
            }
            for c in changes
            if c.strike in keep
        ],
        "summary": (
            f"{ins.symbol} {expiry.isoformat()} OI change on {day} "
            f"{a.ts.astimezone(IST):%H:%M}-{b.ts.astimezone(IST):%H:%M} IST: "
            f"calls {call_total:+d}, puts {put_total:+d}"
        ),
        **provenance(provider, fresh, demo),
    }


# ----------------------------------------------------------------------------- breadth
class BreadthArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    universe: str = Field(default="NIFTY50", max_length=40)
    day: date | None = Field(default=None, description="IST date; default the latest stored")


@REGISTRY.register(
    "breadth",
    "Stored daily market breadth for a universe (advances, declines, 52-week highs/lows, "
    "% above EMA50/EMA200, index moves) from the active provider's daily candles.",
    "green",
    BreadthArgs,
)
async def breadth(ctx: ActionContext, args: BreadthArgs) -> dict[str, Any]:
    u = args.universe.strip().upper()
    if u not in UNIVERSES:
        raise ActionError(
            f"unknown universe {args.universe!r}; known: {', '.join(sorted(UNIVERSES))}"
        )
    provider, demo = await active_provider(ctx)
    await _provider_db_id(ctx, provider)
    db = ctx.session()
    if args.day is not None:
        found = await list_breadth(
            db, provider=provider, universe=u, start=args.day, end=args.day, limit=1
        )
        row = found[0] if found else None
    else:
        row = await latest_breadth(db, provider=provider, universe=u)
    if row is None:
        when = args.day.isoformat() if args.day else "any day"
        return {
            "universe": u,
            "status": "no_data",
            "summary": f"no breadth stored for {u} ({when}) from {provider}",
            **provenance(provider, NONE, demo),
        }
    fresh = Freshness.DEMO.value if demo else Freshness.HISTORICAL.value
    return {
        "universe": u,
        "status": "ok",
        "as_of_date": row.as_of_date.isoformat(),
        "membership_as_of": NIFTY50_AS_OF.isoformat(),
        "universe_size": row.universe_size,
        "advances": row.advances,
        "declines": row.declines,
        "unchanged": row.unchanged,
        "new_52w_high": row.new_52w_high,
        "new_52w_low": row.new_52w_low,
        "above_ema50_pct": _f(row.above_ema50_pct),
        "above_ema200_pct": _f(row.above_ema200_pct),
        "index_moves": row.index_moves or {},
        "computed_at": row.computed_at.isoformat(),
        "summary": (
            f"{u} {row.as_of_date}: {row.advances} up / {row.declines} down / "
            f"{row.unchanged} flat, {row.new_52w_high} 52w highs, {row.new_52w_low} 52w lows"
        ),
        **provenance(provider, fresh, demo),
    }


# ----------------------------------------------------------------------------- scanner
class ScanCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str = Field(min_length=1, max_length=40)
    op: str = Field(min_length=1, max_length=12)
    value: Any = None


class ScannerArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preset: str | None = Field(
        default=None, max_length=80, description="preset name, e.g. 'Top gainers'"
    )
    all: list[ScanCondition] = Field(default_factory=list, max_length=20)
    any: list[ScanCondition] = Field(default_factory=list, max_length=20)
    sort_field: str | None = Field(default=None, max_length=40)
    sort_dir: Literal["asc", "desc"] = "desc"
    columns: list[str] | None = Field(default=None, max_length=20)
    limit: int = Field(default=25, ge=1, le=100)
    as_of: date | None = None


def preset_names() -> list[str]:
    return [str(p["name"]) for p in PRESETS]


@REGISTRY.register(
    "scanner_run",
    "Run a preset scan or ad-hoc filters (field/op/value, all + any) over the latest stored "
    "nightly scanner snapshot of the active provider; deterministic, read only.",
    "green",
    ScannerArgs,
)
async def scanner_run(ctx: ActionContext, args: ScannerArgs) -> dict[str, Any]:
    if args.preset:
        match = [p for p in PRESETS if str(p["name"]).lower() == args.preset.strip().lower()]
        if not match:
            raise ActionError(
                f"unknown preset {args.preset!r}; presets: {', '.join(preset_names())}"
            )
        spec: dict[str, Any] = {
            "filters": match[0]["filters"],
            "sort": match[0]["sort"],
            "columns": args.columns or match[0]["columns"],
        }
    else:
        spec = {
            "filters": {
                "all": [c.model_dump() for c in args.all],
                "any": [c.model_dump() for c in args.any],
            },
            "sort": {"field": args.sort_field, "dir": args.sort_dir} if args.sort_field else None,
            "columns": args.columns,
        }
    spec["limit"] = args.limit
    try:
        query = ScanQuery.from_dict(spec)
    except (ScanQueryError, KeyError, TypeError, ValueError) as exc:
        raise ActionError(f"bad scan: {exc}") from exc
    provider, demo = await active_provider(ctx)
    await _provider_db_id(ctx, provider)
    snap = await latest_scan_snapshot(ctx.session(), provider, args.as_of)
    if snap is None:
        return {
            "status": "no_data",
            "rows": [],
            "total": 0,
            "summary": f"no scanner snapshot stored for {provider}"
            + (f" on {args.as_of}" if args.as_of else ""),
            **provenance(provider, NONE, demo),
        }
    rows, total = apply_query(snap.rows, query)
    fresh = Freshness.DEMO.value if demo else Freshness.HISTORICAL.value
    return {
        "status": "ok",
        "preset": args.preset,
        "as_of": snap.as_of_date.isoformat(),
        "computed_at": snap.computed_at.isoformat(),
        "total": total,
        "columns": list(query.columns),
        "rows": rows,
        "summary": f"{total} match(es) on the {snap.as_of_date} snapshot, showing {len(rows)}",
        **provenance(provider, fresh, demo),
    }


# ----------------------------------------------------------------------------- backtests
HEADLINE_METRICS = (
    "total_return_pct",
    "cagr_pct",
    "sharpe",
    "max_drawdown_pct",
    "win_rate_pct",
    "profit_factor",
    "total_trades",
    "final_equity",
)


class BacktestArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: int | None = Field(default=None, ge=1)
    limit: int = Field(default=10, ge=1, le=50)


def _job_dict(j: BacktestJob) -> dict[str, Any]:
    return {
        "id": j.id,
        "strategy_version_id": j.strategy_version_id,
        "instrument_id": j.instrument_id,
        "timeframe": str(j.timeframe.value if hasattr(j.timeframe, "value") else j.timeframe),
        "start_at": j.start_at.isoformat(),
        "end_at": j.end_at.isoformat(),
        "status": str(j.status.value if hasattr(j.status, "value") else j.status),
        "label": j.label,
        "queued_at": j.queued_at.isoformat(),
        "finished_at": j.finished_at.isoformat() if j.finished_at else None,
        "error": j.error,
    }


@REGISTRY.register(
    "backtest_results",
    "Recent backtest jobs with status and headline metrics, or the metrics, assumptions "
    "and warnings of one job. Read only: it never starts a backtest.",
    "green",
    BacktestArgs,
)
async def backtest_results(ctx: ActionContext, args: BacktestArgs) -> dict[str, Any]:
    db = ctx.session()
    provider, demo = await active_provider(ctx)
    src = f"backtest_results (worker runs on the active provider, {provider})"
    fresh = Freshness.DEMO.value if demo else Freshness.HISTORICAL.value
    if args.job_id is not None:
        j = await db.get(BacktestJob, args.job_id)
        if j is None or (ctx.user_id is not None and j.user_id != ctx.user_id):
            raise ActionError(f"backtest job {args.job_id} not found")
        r = (
            await db.execute(select(BacktestResult).where(BacktestResult.job_id == j.id))
        ).scalar_one_or_none()
        if r is None:
            return {
                "job": _job_dict(j),
                "status": "no_result",
                "summary": f"backtest {j.id} has no result ({_job_dict(j)['status']})",
                **provenance(src, NONE, demo),
            }
        return {
            "job": _job_dict(j),
            "status": "ok",
            "metrics": r.metrics,
            "assumptions": r.assumptions,
            "warnings": list(r.warnings or []),
            "data_hash": r.data_hash,
            "summary": f"backtest {j.id}: "
            + ", ".join(f"{k} {r.metrics.get(k)}" for k in HEADLINE_METRICS if k in r.metrics),
            **provenance(src, fresh, demo),
        }
    q = (
        select(BacktestJob, BacktestResult.metrics)
        .outerjoin(BacktestResult, BacktestResult.job_id == BacktestJob.id)
        .order_by(BacktestJob.queued_at.desc())
        .limit(args.limit)
    )
    if ctx.user_id is not None:
        q = q.where(BacktestJob.user_id == ctx.user_id)
    jobs = []
    for j, metrics in (await db.execute(q)).all():
        d = _job_dict(j)
        d["metrics"] = (
            {k: metrics.get(k) for k in HEADLINE_METRICS if k in metrics} if metrics else None
        )
        jobs.append(d)
    return {
        "jobs": jobs,
        "status": "ok" if jobs else "no_data",
        "summary": f"{len(jobs)} recent backtest job(s)" if jobs else "no backtest jobs stored",
        **provenance(src, fresh if jobs else NONE, demo),
    }


# ----------------------------------------------------------------------------- paper
async def _paper_freshness(ctx: ActionContext, demo: bool) -> tuple[str, str]:
    """Paper positions are marked by the paper trader from the active provider's quotes."""
    now = ctx.now()
    if demo:
        return Freshness.DEMO.value, "marked from demo prices"
    if not nse_calendar().is_open(now):
        return Freshness.HISTORICAL.value, "market closed: last mark of the session"
    tr = await trader_status(ctx, now)
    if tr["status"] == "ok":
        return Freshness.DELAYED.value, "marked by the paper trader (refresh ~10 s)"
    return Freshness.STALE.value, f"paper trader {tr['status']}: marks may be old"


@REGISTRY.register(
    "paper_positions",
    "Open paper positions across the active paper accounts: symbol, quantity, average and "
    "last price, unrealised P&L. Paper only; live positions are not served.",
    "green",
)
async def paper_positions(ctx: ActionContext, _: NoArgs) -> dict[str, Any]:
    db = ctx.session()
    provider, demo = await active_provider(ctx)
    accounts = await _accounts(ctx)
    ids = [a.id for a in accounts]
    pos = (
        list(
            (
                await db.execute(
                    select(PaperPosition)
                    .where(
                        PaperPosition.paper_account_id.in_(ids),
                        PaperPosition.closed_at.is_(None),
                        PaperPosition.quantity != 0,
                    )
                    .order_by(PaperPosition.id)
                )
            )
            .scalars()
            .all()
        )
        if ids
        else []
    )
    sym = await _symbols(ctx, {p.instrument_id for p in pos})
    names = {a.id: a.name for a in accounts}
    rows = [
        {
            "id": p.id,
            "paper_account_id": p.paper_account_id,
            "account": names.get(p.paper_account_id),
            "symbol": sym.get(p.instrument_id),
            "instrument_id": p.instrument_id,
            "quantity": p.quantity,
            "avg_price": p.avg_price,
            "last_price": p.last_price,
            "unrealized_pnl": p.unrealized_pnl,
            "activation_id": p.activation_id,
        }
        for p in pos
    ]
    fresh, note = await _paper_freshness(ctx, demo)
    unreal = sum((p.unrealized_pnl for p in pos), Decimal("0"))
    return {
        "mode": "paper",
        "positions": rows,
        "accounts": len(accounts),
        "unrealized_total": unreal,
        "note": note,
        "summary": (
            "no open paper positions"
            if not rows
            else f"{len(rows)} open paper position(s), unrealised {unreal:.2f}"
        ),
        **provenance(f"paper_positions ({provider} marks)", fresh if rows else NONE, demo),
    }


class PnlArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period: Literal["day", "week", "month", "custom"] = "day"
    start: date | None = Field(default=None, description="IST date, period=custom")
    end: date | None = Field(default=None, description="IST date inclusive, period=custom")


def _period(args: PnlArgs, now: datetime) -> tuple[date, date]:
    today = now.astimezone(IST).date()
    if args.period == "day":
        return today, today
    if args.period == "week":
        return today - timedelta(days=today.weekday()), today
    if args.period == "month":
        return today.replace(day=1), today
    if args.start is None:
        raise ActionError("period=custom needs start (and optionally end)")
    end = args.end or today
    if end < args.start:
        raise ActionError("end is before start")
    if (end - args.start).days > 366:
        raise ActionError("custom period is limited to one year")
    return args.start, end


@REGISTRY.register(
    "paper_pnl",
    "Paper P&L for a period (day, week, month or custom IST dates): realised net P&L from "
    "closed paper trades, trade and win counts, plus the open unrealised P&L now. Paper only.",
    "green",
    PnlArgs,
)
async def paper_pnl(ctx: ActionContext, args: PnlArgs) -> dict[str, Any]:
    db = ctx.session()
    now = ctx.now()
    d0, d1 = _period(args, now)
    lo = ist_day_bounds(datetime.combine(d0, time(12), tzinfo=IST))[0]
    hi = ist_day_bounds(datetime.combine(d1, time(12), tzinfo=IST))[1]
    provider, demo = await active_provider(ctx)
    accounts = await _accounts(ctx)
    out: list[dict[str, Any]] = []
    for a in accounts:
        realized, trades, wins = (
            await db.execute(
                select(
                    func.coalesce(func.sum(PaperTrade.net_pnl), 0),
                    func.count(PaperTrade.id),
                    func.count(PaperTrade.id).filter(PaperTrade.net_pnl > 0),
                ).where(
                    PaperTrade.paper_account_id == a.id,
                    PaperTrade.exit_at >= lo,
                    PaperTrade.exit_at < hi,
                )
            )
        ).one()
        unreal = (
            await db.execute(
                select(func.coalesce(func.sum(PaperPosition.unrealized_pnl), 0)).where(
                    PaperPosition.paper_account_id == a.id,
                    PaperPosition.closed_at.is_(None),
                    PaperPosition.quantity != 0,
                )
            )
        ).scalar_one()
        out.append(
            {
                "id": a.id,
                "name": a.name,
                "currency": a.currency,
                "realized": Decimal(realized),
                "trades_closed": int(trades),
                "wins": int(wins),
                "unrealized_open": Decimal(unreal),
                "cash": a.cash,
            }
        )
    fresh, note = await _paper_freshness(ctx, demo)
    total = sum((a["realized"] for a in out), Decimal("0"))
    n = sum(a["trades_closed"] for a in out)
    return {
        "mode": "paper",
        "period": args.period,
        "from": d0.isoformat(),
        "to": d1.isoformat(),
        "accounts": out,
        "realized_total": total,
        "trades_closed": n,
        "note": note,
        "summary": (
            "no active paper accounts"
            if not out
            else f"paper realised {total:.2f} over {n} closed trade(s), {d0} to {d1} (IST)"
        ),
        **provenance(f"paper_trades ({provider} marks)", fresh if out else NONE, demo),
    }


# ----------------------------------------------------------------------------- reports, news
class ReportArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    day: date | None = Field(default=None, description="IST date; default the latest report")


@REGISTRY.register(
    "daily_report",
    "The stored end-of-day report / evening brief (latest, or for one IST date): its "
    "markdown text and the structured facts it was rendered from.",
    "green",
    ReportArgs,
)
async def daily_report(ctx: ActionContext, args: ReportArgs) -> dict[str, Any]:
    q = select(DailyReport).order_by(DailyReport.report_date.desc()).limit(1)
    if args.day is not None:
        q = select(DailyReport).where(
            DailyReport.report_date == args.day, DailyReport.kind == "eod"
        )
    r = (await ctx.session().execute(q)).scalars().first()
    if r is None:
        when = args.day.isoformat() if args.day else "yet"
        return {
            "status": "no_data",
            "summary": f"no daily report stored {('for ' + when) if args.day else when}",
            **provenance("daily_reports", NONE, False),
        }
    prov = str((r.content or {}).get("provider") or "")
    demo = await provider_is_demo(ctx, prov) if prov else False
    return {
        "status": "ok",
        "report_date": r.report_date.isoformat(),
        "kind": r.kind,
        "created_at": r.created_at.isoformat(),
        "text_md": r.text_md,
        "content": r.content,
        "summary": f"{r.kind} report for {r.report_date} (created {r.created_at.isoformat()})",
        **provenance(
            f"daily_reports ({prov or 'provider not recorded'})",
            Freshness.DEMO.value if demo else Freshness.HISTORICAL.value,
            demo,
        ),
    }


class NewsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str | None = Field(default=None, max_length=32)
    hours: int = Field(default=24, ge=1, le=168)
    q: str | None = Field(default=None, max_length=100)
    limit: int = Field(default=20, ge=1, le=50)


NEWS_SCAN_CAP = 3000


@REGISTRY.register(
    "news",
    "Recent raw news headlines from the configured RSS feeds (newest first), optionally only "
    "those tagged with one symbol by the deterministic matcher. Headlines only, no AI.",
    "green",
    NewsArgs,
)
async def news(ctx: ActionContext, args: NewsArgs) -> dict[str, Any]:
    db = ctx.session()
    since = ctx.now() - timedelta(hours=args.hours)
    sym = _clean(args.symbol) if args.symbol else None
    provider, _demo = await active_provider(ctx)
    matcher = await matcher_for(db, provider)
    rows = await list_news(db, since=since, q=args.q, limit=NEWS_SCAN_CAP if sym else args.limit)
    items: list[dict[str, Any]] = []
    for r in rows:
        tags = matcher.tags(r.title, r.summary)
        if sym and sym not in tags:
            continue
        d = item_dict(r, tags)
        items.append({k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in d.items()})
        if len(items) >= args.limit:
            break
    what = f" about {sym}" if sym else ""
    return {
        "items": items,
        "symbol": sym,
        "summary": (
            f"{len(items)} headline(s){what} in the last {args.hours} h"
            if items
            else f"no headlines{what} in the last {args.hours} h"
        ),
        # Headlines are third-party text, not market data: no market source, never demo.
        **provenance("news_items (RSS headlines; no market source)", NONE, False),
    }


# ----------------------------------------------------------------------------- protocols, rules
class ProtocolStatusArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{1,47}$")
    limit: int = Field(default=10, ge=1, le=50)


@REGISTRY.register(
    "protocol_status",
    "Recent protocol runs (newest first): protocol, status, trigger, start/finish time, "
    "summary and per-step outcome counts. Read only: it never starts or confirms a run.",
    "green",
    ProtocolStatusArgs,
)
async def protocol_status(ctx: ActionContext, args: ProtocolStatusArgs) -> dict[str, Any]:
    q = (
        select(ProtocolRun, Protocol.code, Protocol.name)
        .join(Protocol, Protocol.id == ProtocolRun.protocol_id)
        .order_by(ProtocolRun.started_at.desc(), ProtocolRun.id.desc())
        .limit(args.limit)
    )
    if ctx.user_id is not None:
        q = q.where((ProtocolRun.user_id == ctx.user_id) | ProtocolRun.user_id.is_(None))
    if args.code:
        q = q.where(Protocol.code == args.code)
    runs = []
    for r, code, name in (await ctx.session().execute(q)).all():
        counts: dict[str, int] = {}
        for s in r.steps or []:
            st = str(s.get("status", "planned")) if isinstance(s, dict) else "planned"
            counts[st] = counts.get(st, 0) + 1
        runs.append(
            {
                "id": r.id,
                "code": code,
                "name": name,
                "status": r.status,
                "trigger": r.trigger,
                "started_at": r.started_at.isoformat(),
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                "summary": r.summary,
                "steps": counts,
            }
        )
    return {
        "runs": runs,
        "summary": (
            f"{len(runs)} recent run(s); newest {runs[0]['code']} {runs[0]['status']}"
            if runs
            else "no protocol runs stored"
        ),
        **provenance("protocol_runs (platform state; no market source)", NONE, False),
    }


@REGISTRY.register(
    "owner_rules",
    "The owner's hard trading rules (docs/trading-rules.md) as registered in the risk "
    "engine: code, description and the thresholds they use. They block entries in every mode "
    "and cannot be bypassed.",
    "green",
)
async def owner_rules(ctx: ActionContext, _: NoArgs) -> dict[str, Any]:
    lim = RiskLimits()
    rules = [{"code": r.code, "description": r.description} for r in OWNER_RULES]
    return {
        "rules": rules,
        "thresholds": {
            "pcr_no_put_buy_at": lim.pcr_no_put_buy_at,
            "pcr_no_call_buy_at": lim.pcr_no_call_buy_at,
            "pcr_max_age_minutes": lim.pcr_max_age_minutes,
        },
        "document": TRADING_RULES_DOC,
        "summary": f"{len(rules)} hard rule(s): " + ", ".join(r["code"] for r in rules),
        **provenance("risk.owner_rules registry (no market source)", NONE, False),
    }
