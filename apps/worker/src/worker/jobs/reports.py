"""Evening brief job (Mark 1 Stage 3.3 + 3.7): gather the day's facts from stored data, store
one `daily_reports` row per day (regenerating replaces it) and send it to Telegram when a bot
is configured. No AI; every missing source is reported as missing."""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.calendar import nse_calendar
from core.db import get_session_factory
from core.db.models import (
    Alert,
    Contract,
    DailyReport,
    MarketBreadth,
    NewsItem,
    PaperAccount,
    PaperPosition,
    PaperTrade,
)
from core.logging import get_logger
from core.models import Timeframe
from core.notify import build_notifier
from core.settings import get_settings
from core.time import IST, utcnow
from market_data.repo._lookup import provider_id
from market_data.repo.candles import fetch_candles
from market_data.repo.chains import latest_chain_oi
from market_data.repo.instruments import get_by_symbol
from risk.owner_rules import pcr_from_oi
from worker.reports.evening_brief import (
    FULL_SESSION_MINUTES,
    AccountDay,
    Coverage,
    Facts,
    IndexMove,
    PcrReading,
    build_content,
    render_markdown,
)

log = get_logger(__name__)

INDICES = ("NIFTY", "BANKNIFTY", "INDIAVIX")
PCR_UNDERLYINGS = ("NIFTY", "BANKNIFTY")
KIND = "eod"


def _symbols(raw: str) -> list[str]:
    return [s.strip().upper() for s in raw.split(",") if s.strip()]


async def _index_moves(
    db: AsyncSession, day: date, prev_day: date, provider: str
) -> list[IndexMove]:
    cal = nse_calendar()
    out: list[IndexMove] = []
    for sym in INDICES:
        ins = await get_by_symbol(db, "NSE", sym)
        if ins is None:
            continue
        close: Decimal | None = None
        bounds = cal.session_bounds_utc(day)
        if bounds:
            bars = await fetch_candles(
                db,
                ins.instrument_id,
                Timeframe.M1,
                bounds[0],
                bounds[1] + timedelta(minutes=1),
                provider,
            )
            close = bars[-1].close if bars else None
        if close is None:
            d1 = await fetch_candles(
                db,
                ins.instrument_id,
                Timeframe.D1,
                datetime.combine(day, datetime.min.time(), IST),
                datetime.combine(day + timedelta(days=1), datetime.min.time(), IST),
                provider,
            )
            close = d1[-1].close if d1 else None
        prev = await fetch_candles(
            db,
            ins.instrument_id,
            Timeframe.D1,
            datetime.combine(prev_day, datetime.min.time(), IST),
            datetime.combine(prev_day + timedelta(days=1), datetime.min.time(), IST),
            provider,
        )
        out.append(IndexMove(sym, close, prev[-1].close if prev else None))
    return out


async def _pcr(db: AsyncSession, day: date) -> list[PcrReading]:
    cal = nse_calendar()
    bounds = cal.session_bounds_utc(day)
    at = bounds[1] if bounds else datetime.combine(day, datetime.max.time(), IST)
    out: list[PcrReading] = []
    for sym in PCR_UNDERLYINGS:
        ins = await get_by_symbol(db, "NSE", sym)
        if ins is None:
            continue
        oi = await latest_chain_oi(db, ins.instrument_id, at)
        if oi is None:
            out.append(PcrReading(sym, None, None, None))
        else:
            out.append(
                PcrReading(
                    sym,
                    pcr_from_oi(oi.put_oi, oi.call_oi),
                    oi.expiry.astimezone(IST).date().isoformat(),
                    oi.ts,
                )
            )
    return out


async def _breadth(db: AsyncSession, day: date, provider: str) -> dict[str, Any] | None:
    pid = await provider_id(db, provider)
    row = (
        await db.execute(
            select(MarketBreadth).where(
                MarketBreadth.as_of_date == day,
                MarketBreadth.universe == "NIFTY50",
                MarketBreadth.provider_id == pid,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    return {
        "advances": row.advances,
        "declines": row.declines,
        "unchanged": row.unchanged,
        "new_52w_high": row.new_52w_high,
        "new_52w_low": row.new_52w_low,
        "above_ema200_pct": str(row.above_ema200_pct) if row.above_ema200_pct is not None else None,
    }


async def _accounts(db: AsyncSession, start: datetime, end: datetime) -> list[AccountDay]:
    out: list[AccountDay] = []
    accts = (
        await db.execute(select(PaperAccount).where(PaperAccount.is_active.is_(True)))
    ).scalars()
    for a in accts:
        trades = (
            (
                await db.execute(
                    select(PaperTrade).where(
                        PaperTrade.paper_account_id == a.id,
                        PaperTrade.exit_at >= start,
                        PaperTrade.exit_at < end,
                    )
                )
            )
            .scalars()
            .all()
        )
        open_n = (
            await db.execute(
                select(func.count()).where(
                    PaperPosition.paper_account_id == a.id, PaperPosition.quantity != 0
                )
            )
        ).scalar_one()
        out.append(
            AccountDay(
                account_id=a.id,
                name=a.name,
                cash=a.cash,
                trades=len(trades),
                wins=sum(1 for t in trades if t.net_pnl > 0),
                net_pnl=sum((t.net_pnl for t in trades), Decimal("0")),
                open_positions=int(open_n),
            )
        )
    return out


async def _alerts(db: AsyncSession, start: datetime, end: datetime) -> tuple[dict[str, int], int]:
    rows = (
        await db.execute(
            select(Alert.severity, Alert.kind).where(Alert.ts >= start, Alert.ts < end)
        )
    ).all()
    sev = Counter(r.severity for r in rows)
    return dict(sev), sum(1 for r in rows if r.kind == "rule_block")


async def _coverage(db: AsyncSession, day: date, provider: str) -> list[Coverage]:
    cal = nse_calendar()
    bounds = cal.session_bounds_utc(day)
    if bounds is None:
        return []
    expected = int((bounds[1] - bounds[0]).total_seconds() // 60) or FULL_SESSION_MINUTES
    out: list[Coverage] = []
    for sym in _symbols(get_settings().collect_symbols):
        ins = await get_by_symbol(db, "NSE", sym)
        if ins is None:
            continue
        bars = await fetch_candles(
            db, ins.instrument_id, Timeframe.M1, bounds[0], bounds[1], provider
        )
        out.append(Coverage(sym, len(bars), expected))
    return out


async def _expiries(db: AsyncSession, day: date) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for sym in PCR_UNDERLYINGS:
        ins = await get_by_symbol(db, "NSE", sym)
        if ins is None:
            continue
        exps = (
            await db.execute(
                select(Contract.expiry)
                .where(
                    Contract.underlying_id == ins.instrument_id,
                    Contract.expiry > day,
                    Contract.expiry <= day + timedelta(days=7),
                )
                .distinct()
                .order_by(Contract.expiry)
            )
        ).scalars()
        out.extend({"symbol": sym, "expiry": e.isoformat()} for e in exps)
    return out


async def _headlines(db: AsyncSession, start: datetime, end: datetime) -> list[dict[str, str]]:
    rows = (
        await db.execute(
            select(NewsItem)
            .where(NewsItem.published_at >= start, NewsItem.published_at < end)
            .order_by(NewsItem.published_at.desc())
            .limit(8)
        )
    ).scalars()
    return [{"title": n.title, "source": n.source, "url": n.url} for n in rows]


async def gather(db: AsyncSession, day: date) -> Facts:
    cal = nse_calendar()
    provider = get_settings().default_market_data_provider
    start = datetime.combine(day, datetime.min.time(), IST)
    end = start + timedelta(days=1)
    sev, blocks = await _alerts(db, start, end)
    return Facts(
        day=day,
        is_trading_day=cal.is_trading_day(day),
        provider=provider,
        indices=await _index_moves(db, day, cal.previous_trading_day(day), provider),
        pcr=await _pcr(db, day),
        breadth=await _breadth(db, day, provider),
        accounts=await _accounts(db, start, end),
        alerts_by_severity=sev,
        rule_blocks=blocks,
        coverage=await _coverage(db, day, provider),
        next_trading_day=cal.next_trading_day(day),
        expiries_next_7d=await _expiries(db, day),
        headlines=await _headlines(db, start, end),
    )


async def generate_evening_brief(
    ctx: dict[str, Any], day: str | None = None, send: bool = True
) -> dict[str, Any]:
    """Build, store (replacing the day's row) and optionally send the brief."""
    cal = nse_calendar()
    target = date.fromisoformat(day) if day else utcnow().astimezone(IST).date()
    if day is None and not cal.is_trading_day(target):
        return {"skipped": f"{target} is not a trading day"}
    settings = get_settings()
    async with get_session_factory()() as db:
        content = build_content(await gather(db, target))
        text = render_markdown(content)
        delivered: dict[str, Any] = {"in_app": True, "telegram": "skipped"}
        if send:
            try:
                ok = await build_notifier(settings).send(text)
                delivered["telegram"] = "sent" if ok else "skipped"
            except Exception as exc:  # delivery must not lose the stored report
                delivered["telegram"] = "failed"
                log.warning("evening_brief.telegram_failed", error=str(exc))
        stmt = insert(DailyReport).values(
            report_date=target, kind=KIND, content=content, text_md=text, delivered=delivered
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["report_date", "kind"],
            set_={
                "content": stmt.excluded.content,
                "text_md": stmt.excluded.text_md,
                "delivered": stmt.excluded.delivered,
                "created_at": func.now(),
            },
        )
        await db.execute(stmt)
        await db.commit()
    log.info("evening_brief.stored", day=target.isoformat(), telegram=delivered["telegram"])
    return {"day": target.isoformat(), "delivered": delivered}
