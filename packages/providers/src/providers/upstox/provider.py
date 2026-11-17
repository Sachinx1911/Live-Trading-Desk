"""Upstox MarketDataProvider.

The access token lives elsewhere (encrypted in broker_sessions); this class receives a
getter. Instrument ids: `fetch_instruments()` returns provisional ids (1_000_000+) which
`market_data.sync` reconciles against the DB; the manager/collector then calls
`bind_mapping({db_instrument_id: instrument_key})` so quotes/feed/candles can be requested
by canonical id.
"""

from __future__ import annotations

import gzip
import json
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from datetime import date, datetime, timedelta
from typing import Any

import httpx

from core.models import Candle, Instrument, OptionChainSnapshot, Quote, Tick, Timeframe
from core.time import IST, ensure_utc, utcnow
from providers import registry
from providers.base import (
    ConnectionState,
    MarketDataProvider,
    ProviderCapability,
    ProviderHealth,
    ProviderInfo,
)
from providers.upstox.auth import UpstoxAuth
from providers.upstox.client import API_BASE, UpstoxRest
from providers.upstox.errors import UpstoxAuthError, UpstoxError
from providers.upstox.feed import FeedStats, UpstoxFeed
from providers.upstox.mapping import (
    HISTORICAL_LIMITS,
    TF_UNIT,
    chunk_ranges,
    map_candles,
    map_instruments,
    map_option_chain,
    map_quotes,
)

INSTRUMENTS_URL = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
QUOTE_BATCH = 500

_INFO = ProviderInfo(
    code="upstox",
    display_name="Upstox",
    capabilities=frozenset(
        {
            ProviderCapability.LIVE_QUOTES,
            ProviderCapability.LIVE_TICKS,
            ProviderCapability.MARKET_DEPTH,
            ProviderCapability.HISTORICAL_CANDLES,
            ProviderCapability.OPTION_CHAIN,
            ProviderCapability.INSTRUMENT_MASTER,
            ProviderCapability.ORDERS,
        }
    ),
    is_demo=False,
    supported_timeframes=frozenset(TF_UNIT),
)


class UpstoxMarketDataProvider(MarketDataProvider):
    historical_limits = HISTORICAL_LIMITS

    def __init__(
        self,
        access_token_getter: Callable[[], str | None],
        *,
        token_expiry_getter: Callable[[], datetime | None] | None = None,
        client_id: str = "",
        client_secret: str = "",
        redirect_uri: str = "",
        base_url: str = API_BASE,
        instruments_url: str = INSTRUMENTS_URL,
        transport: httpx.AsyncBaseTransport | None = None,
        feed_mode: str = "full",
    ) -> None:
        self._token_getter = access_token_getter
        self._expiry_getter = token_expiry_getter or (lambda: None)
        self._base = base_url
        self._instruments_url = instruments_url
        self._transport = transport
        self._feed_mode = feed_mode
        self.rest = UpstoxRest(access_token_getter, base_url=base_url, transport=transport)
        self.auth = UpstoxAuth(
            client_id,
            client_secret,
            redirect_uri,
            base_url=base_url,
            transport=transport,
        )
        self.key_by_provisional_id: dict[int, str] = {}
        self._key_by_id: dict[int, str] = {}
        self._id_by_key: dict[str, int] = {}
        self._connected = False
        self._feed_stats = FeedStats()
        self._feed: UpstoxFeed | None = None

    # -- identity --------------------------------------------------------------------
    @property
    def info(self) -> ProviderInfo:
        return _INFO

    def bind_mapping(self, key_by_instrument_id: Mapping[int, str]) -> None:
        """Attach DB instrument ids ↔ Upstox instrument keys (called after sync)."""
        self._key_by_id.update(key_by_instrument_id)
        self._id_by_key.update({k: i for i, k in key_by_instrument_id.items()})

    def instrument_key(self, instrument_id: int) -> str:
        try:
            return self._key_by_id[instrument_id]
        except KeyError:
            try:
                return self.key_by_provisional_id[instrument_id]
            except KeyError as exc:
                raise UpstoxError(f"no Upstox key bound for instrument {instrument_id}") from exc

    def provider_token(self, instrument: Instrument) -> str:
        """Token stored in instrument_mappings (market_data.sync hook): the instrument_key."""
        return self.provider_key_for(instrument)

    def provider_key_for(self, instrument: Instrument) -> str:
        return self.instrument_key(instrument.instrument_id)

    # -- lifecycle -------------------------------------------------------------------
    async def connect(self) -> None:
        if not self._token_getter():
            self._connected = False
            raise UpstoxAuthError("no access token; daily login required")
        self._connected = True

    async def disconnect(self) -> None:
        if self._feed is not None:
            self._feed.stop()
        self._connected = False
        await self.rest.aclose()

    def _token_valid(self) -> bool:
        token = self._token_getter()
        if not token:
            return False
        exp = self._expiry_getter()
        return exp is None or ensure_utc(exp) > utcnow()

    async def health(self) -> ProviderHealth:
        exp = self._expiry_getter()
        if not self._token_valid():
            return ProviderHealth(
                code="upstox",
                state=ConnectionState.AUTH_REQUIRED,
                message="Upstox login required (token missing or expired)",
                session_valid_until=exp,
            )
        if self._feed_stats.last_error == "auth_required":
            state = ConnectionState.AUTH_REQUIRED
        elif self._feed_stats.connected:
            state = ConnectionState.CONNECTED
        elif self._connected:
            state = ConnectionState.CONNECTED if self._feed is None else ConnectionState.CONNECTING
        else:
            state = ConnectionState.DISCONNECTED
        return ProviderHealth(
            code="upstox",
            state=state,
            last_message_at=self._feed_stats.last_message_at,
            latency_ms=self._feed_stats.latency_ms,
            reconnects_today=self._feed_stats.reconnects_today,
            message=self._feed_stats.last_error,
            session_valid_until=exp,
        )

    # -- instruments -----------------------------------------------------------------
    async def fetch_instruments(self) -> Sequence[Instrument]:
        async with httpx.AsyncClient(transport=self._transport, timeout=60.0) as client:
            resp = await client.get(self._instruments_url)
        if resp.status_code != 200:
            raise UpstoxError(f"instrument master download failed: {resp.status_code}")
        raw = resp.content
        if self._instruments_url.endswith(".gz") or raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        records: list[dict[str, Any]] = json.loads(raw)
        instruments, keys = map_instruments(records)
        self.key_by_provisional_id = keys
        return instruments

    # -- quotes ----------------------------------------------------------------------
    async def get_quotes(self, instrument_ids: Sequence[int]) -> Sequence[Quote]:
        keys = [self.instrument_key(i) for i in instrument_ids]
        out: list[Quote] = []
        for i in range(0, len(keys), QUOTE_BATCH):
            batch = keys[i : i + QUOTE_BATCH]
            body = await self.rest.get_json(
                "/v2/market-quote/quotes", params={"instrument_key": ",".join(batch)}
            )
            out.extend(map_quotes(body, self._lookup_ids(), utcnow()))
        return out

    def _lookup_ids(self) -> dict[str, int]:
        d = {k: i for i, k in self.key_by_provisional_id.items()}
        d.update(self._id_by_key)
        return d

    # -- candles ---------------------------------------------------------------------
    async def get_candles(
        self, instrument_id: int, timeframe: Timeframe, start: datetime, end: datetime
    ) -> Sequence[Candle]:
        if timeframe not in TF_UNIT:
            raise UpstoxError(f"timeframe {timeframe} not supported by Upstox historical API")
        key = self.instrument_key(instrument_id)
        unit, interval = TF_UNIT[timeframe]
        start_d = ensure_utc(start).astimezone(IST).date()
        end_d = ensure_utc(end).astimezone(IST).date()
        today = utcnow().astimezone(IST).date()
        out: list[Candle] = []
        hist_end = min(end_d, today - timedelta(days=1)) if end_d >= today else end_d
        if hist_end >= start_d:
            for a, b in chunk_ranges(start_d, hist_end, self.historical_limits[timeframe]):
                body = await self.rest.get_json(
                    f"/v3/historical-candle/{key}/{unit}/{interval}/{b.isoformat()}/{a.isoformat()}"
                )
                out.extend(map_candles(body, instrument_id, timeframe, utcnow()))
        if end_d >= today and timeframe.is_intraday:
            body = await self.rest.get_json(
                f"/v3/historical-candle/intraday/{key}/{unit}/{interval}"
            )
            out.extend(map_candles(body, instrument_id, timeframe, utcnow()))
        s, e = ensure_utc(start), ensure_utc(end)
        dedup: dict[datetime, Candle] = {c.ts: c for c in out if s <= c.ts <= e}
        return [dedup[k] for k in sorted(dedup)]

    # -- options ---------------------------------------------------------------------
    async def get_option_chain(
        self, underlying_instrument_id: int, expiry: datetime
    ) -> OptionChainSnapshot:
        key = self.instrument_key(underlying_instrument_id)
        exp_date: date = ensure_utc(expiry).astimezone(IST).date()
        body = await self.rest.get_json(
            "/v2/option/chain",
            params={"instrument_key": key, "expiry_date": exp_date.isoformat()},
        )
        return map_option_chain(
            body, underlying_instrument_id, expiry, self._lookup_ids(), utcnow()
        )

    async def get_option_contracts(
        self, underlying_instrument_id: int, expiry: date | str | None = None
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"instrument_key": self.instrument_key(underlying_instrument_id)}
        if expiry is not None:
            params["expiry_date"] = expiry.isoformat() if isinstance(expiry, date) else expiry
        body = await self.rest.get_json("/v2/option/contract", params=params)
        return list(body.get("data") or [])

    # -- feed ------------------------------------------------------------------------
    def stream_ticks(self, instrument_ids: Sequence[int]) -> AsyncIterator[Tick]:
        keys = [self.instrument_key(i) for i in instrument_ids]
        self._feed = UpstoxFeed(
            self.rest,
            keys,
            self._lookup_ids(),
            mode=self._feed_mode,
            stats=self._feed_stats,
        )
        return self._feed.__aiter__()


def register() -> None:
    """Registry factory: a token-less instance; the app wires the real token getter."""
    registry.register("upstox", lambda: UpstoxMarketDataProvider(lambda: None))
