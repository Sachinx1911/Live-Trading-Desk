"""Collector: one provider feed -> 1-minute candles (DB), quote cache (Redis), tick pub/sub,
option-chain snapshots every COLLECT_CHAIN_INTERVAL_S (default 3 minutes), VIX via the normal
tick path, optional raw ticks.

Runs forever; the provider adapter owns reconnects, this loop owns restarts. Everything
it stores carries provider_id / is_demo so demo data can never be mistaken for real.
"""

from __future__ import annotations

import asyncio
import contextlib
import signal
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import orjson
from redis.asyncio import Redis

from collector.raw import RawTickWriter
from collector.tracked import Tracked, parse_symbols, resolve
from core.calendar import nse_calendar
from core.db import get_session_factory
from core.logging import configure_logging, get_logger
from core.models import Candle, Quote, Tick
from core.notify import build_notifier
from core.secrets import SecretBox
from core.services.brokers import BrokerService
from core.settings import Settings, get_settings
from core.time import IST, utcnow
from market_data.binding import bind_provider
from market_data.candles import CandleBuilder
from market_data.repo.candles import upsert_candles
from market_data.repo.chains import expiries_for, write_snapshot
from market_data.repo.quotes import cache_quote, freshness, write_quotes
from market_data.sync import sync_instrument_master
from providers.base import ConnectionState, MarketDataProvider
from providers.registry import create as create_provider

log = get_logger("collector")

TICK_CHANNEL = "market.tick"
CANDLE_CHANNEL = "market.candle"
QUOTE_CACHE_TTL_S = 7 * 24 * 3600  # survives weekends and holidays; freshness says how old


def _quote_from_tick(t: Tick, prev: Quote | None) -> Quote:
    q = Quote(
        instrument_id=t.instrument_id,
        ts=t.ts,
        ltp=t.ltp,
        bid=t.best_bid,
        ask=t.best_ask,
        bid_qty=t.bids[0].quantity if t.bids else None,
        ask_qty=t.asks[0].quantity if t.asks else None,
        volume=t.volume,
        oi=t.oi,
        open=prev.open if prev else None,
        high=max(prev.high, t.ltp)
        if prev and prev.high is not None
        else (prev.high if prev else None),
        low=min(prev.low, t.ltp) if prev and prev.low is not None else (prev.low if prev else None),
        prev_close=prev.prev_close if prev else None,
        provider_id=t.provider_id,
        provider_ts=t.provider_ts,
        received_at=t.received_at,
        is_demo=t.is_demo,
    )
    return q.model_copy(update={"freshness": freshness(q)})


class Collector:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.redis = Redis.from_url(settings.redis_url, decode_responses=False)
        self.cal = nse_calendar()
        self.builder = CandleBuilder(self.cal)
        self.notifier = build_notifier(settings)
        self.provider: MarketDataProvider = self._make_provider()
        self.tracked = Tracked()
        self._quotes: dict[int, Quote] = {}
        self._stop = asyncio.Event()
        self._raw: RawTickWriter | None = (
            RawTickWriter(Path(settings.data_dir) / "ticks") if settings.collect_raw_ticks else None
        )
        self._tokens: dict[str, str] = {}
        self._last_chain_at: datetime | None = None
        self._last_quote_persist: datetime | None = None

    # -- wiring ---------------------------------------------------------------------
    def _make_provider(self) -> MarketDataProvider:
        code = self.settings.default_market_data_provider
        if code == "upstox":
            from providers.upstox.provider import UpstoxMarketDataProvider

            return UpstoxMarketDataProvider(access_token_getter=lambda: self._tokens.get("upstox"))
        return create_provider(code)

    async def _load_tokens(self) -> None:
        try:
            box = SecretBox(self.settings.secrets_key.get_secret_value())
        except ValueError:
            return
        from sqlalchemy import select

        from core.db.models import Broker, BrokerAccount

        async with get_session_factory()() as db:
            svc = BrokerService(db, self.settings, box)
            rows = await db.execute(
                select(BrokerAccount, Broker.code)
                .join(Broker, Broker.id == BrokerAccount.broker_id)
                .where(BrokerAccount.is_active.is_(True))
            )
            for acct, code in rows.all():
                tok = await svc.valid_token(acct.id)
                if tok:
                    self._tokens[code] = tok
                else:
                    self._tokens.pop(code, None)
            await db.commit()

    async def _prepare(self) -> bool:
        """Sync instruments, bind ids, resolve tracked symbols. False if nothing to track."""
        await self._load_tokens()
        h = await self.provider.health()
        if h.state == ConnectionState.AUTH_REQUIRED:
            log.warning("collector.auth_required", provider=self.provider.info.code)
            await self._publish_health()
            return False
        async with get_session_factory()() as db:
            res = await sync_instrument_master(self.provider, db)
            await db.commit()
            bound = await bind_provider(db, self.provider)
            symbols = parse_symbols(self.settings.collect_symbols)
            chains = parse_symbols(self.settings.collect_chain_underlyings)
            self.tracked = await resolve(db, "NSE", symbols, chains)
        await self._seed_quotes()
        log.info(
            "collector.prepared",
            provider=self.provider.info.code,
            instruments_new=res.new,
            bound=bound,
            tracked=[i.symbol for i in self.tracked.instruments],
            missing=self.tracked.missing,
        )
        return bool(self.tracked.instruments)

    async def _seed_quotes(self) -> None:
        """Outside market hours no ticks arrive; publish the provider's last quotes once so
        the UI shows the last close with an honest (stale/delayed) freshness."""
        if not self.tracked.ids:
            return
        try:
            quotes = await self.provider.get_quotes(self.tracked.ids)
        except Exception as exc:
            log.warning("collector.seed_quotes_failed", error=str(exc))
            return
        for q in quotes:
            q = q.model_copy(update={"freshness": freshness(q)})
            self._quotes[q.instrument_id] = q
            await cache_quote(self.redis, q, ttl_s=QUOTE_CACHE_TTL_S)
            await self.redis.publish(TICK_CHANNEL, orjson.dumps(q.model_dump(mode="json")))
        log.info("collector.quotes_seeded", n=len(quotes))

    # -- storage --------------------------------------------------------------------
    async def _store_candles(self, candles: list[Candle]) -> None:
        if not candles:
            return
        async with get_session_factory()() as db:
            await upsert_candles(db, candles)
            await db.commit()
        for c in candles:
            await self.redis.publish(CANDLE_CHANNEL, orjson.dumps(c.model_dump(mode="json")))

    async def _on_tick(self, t: Tick) -> None:
        prev = self._quotes.get(t.instrument_id)
        q = _quote_from_tick(t, prev)
        self._quotes[t.instrument_id] = q
        # Long TTL on purpose: freshness is derived from the quote's own timestamp, so after
        # the close the UI shows the last price as "stale" instead of nothing at all.
        await cache_quote(self.redis, q, ttl_s=QUOTE_CACHE_TTL_S)
        await self.redis.publish(TICK_CHANNEL, orjson.dumps(q.model_dump(mode="json")))
        if self._raw is not None:
            self._raw.add(t)
        await self._store_candles(self.builder.on_tick(t))

    async def _persist_quotes(self, now: datetime) -> None:
        """Quote snapshots to the hypertable every 60 s (short retention, ADR-010)."""
        if self._last_quote_persist and now - self._last_quote_persist < timedelta(seconds=60):
            return
        self._last_quote_persist = now
        if not self._quotes:
            return
        async with get_session_factory()() as db:
            await write_quotes(db, list(self._quotes.values()), now)
            await db.commit()

    async def _chain_snapshots(self, now: datetime) -> None:
        interval = timedelta(seconds=self.settings.collect_chain_interval_s)
        if self._last_chain_at and now - self._last_chain_at < interval:
            return
        if not self.cal.is_open(now) and self.provider.info.code != "fake":
            return
        if not self.tracked.chain_underlyings:
            return  # not prepared yet; try again next tick
        self._last_chain_at = now
        today = now.astimezone(IST).date()
        async with get_session_factory()() as db:
            for und in self.tracked.chain_underlyings:
                exps = await expiries_for(db, und.instrument_id, today)
                for exp in exps[:2]:  # current + next expiry
                    exp_dt = datetime.combine(exp, datetime.min.time(), tzinfo=IST).replace(
                        hour=15, minute=30
                    )
                    try:
                        snap = await self.provider.get_option_chain(und.instrument_id, exp_dt)
                    except Exception as exc:
                        log.warning("collector.chain_failed", symbol=und.symbol, error=str(exc))
                        continue
                    await write_snapshot(db, snap)
                    log.info(
                        "collector.chain", symbol=und.symbol, expiry=str(exp), rows=len(snap.rows)
                    )
            await db.commit()

    async def _publish_health(self) -> None:
        h = await self.provider.health()
        payload: dict[str, Any] = {
            "provider": h.code,
            "state": h.state.value,
            "last_message_at": h.last_message_at.isoformat() if h.last_message_at else None,
            "latency_ms": h.latency_ms,
            "reconnects_today": h.reconnects_today,
            "message": h.message,
            "is_demo": self.provider.info.is_demo,
            "tracked": [i.symbol for i in self.tracked.instruments],
            "builder": {
                "ticks": self.builder.stats.ticks,
                "late": getattr(self.builder.stats, "late", None),
                "outside_session": self.builder.stats.outside_session,
            },
            "updated_at": utcnow().isoformat(),
        }
        await self.redis.set("collector:health", orjson.dumps(payload), ex=30)

    # -- loops ----------------------------------------------------------------------
    async def _housekeeping(self) -> None:
        while not self._stop.is_set():
            now = utcnow()
            try:
                await self._store_candles(self.builder.on_time(now))
                await self._persist_quotes(now)
                await self._chain_snapshots(now)
                await self._publish_health()
                if self._raw is not None and now.second < 5:
                    self._raw.flush()
            except Exception as exc:
                log.warning("collector.housekeeping_error", error=str(exc))
            await asyncio.sleep(5)

    async def _stream(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            try:
                if not await self._prepare():
                    await asyncio.sleep(60)
                    continue
                await self.provider.connect()
                backoff = 1.0
                async for tick in self.provider.stream_ticks(self.tracked.ids):
                    await self._on_tick(tick)
                    if self._stop.is_set():
                        break
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.error("collector.stream_error", error=str(exc), backoff=backoff)
                await self.notifier.send(f"Collector feed error: {exc}", level="warning")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)
            finally:
                with contextlib.suppress(Exception):
                    await self.provider.disconnect()

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self._stop.set)
            except NotImplementedError:  # Windows: the proactor loop has no signal handlers
                signal.signal(sig, lambda *_: loop.call_soon_threadsafe(self._stop.set))
        log.info("collector.started", provider=self.settings.default_market_data_provider)
        tasks = [asyncio.create_task(self._stream()), asyncio.create_task(self._housekeeping())]
        await self._stop.wait()
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await self._store_candles(self.builder.flush())
        if self._raw is not None:
            self._raw.flush()
        await self.redis.aclose()
        log.info("collector.stopped")


def main() -> None:
    s = get_settings()
    configure_logging(s.log_level, s.log_json)
    asyncio.run(Collector(s).run())


if __name__ == "__main__":
    main()
