"""Fake market data provider: a seeded geometric random walk over a small NSE-like universe.

Used for development, UI states and tests. Never real data; every record carries
``provider_id="fake"`` and ``is_demo=True``.
"""

from __future__ import annotations

import asyncio
import math
import random
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from core.calendar import nse_calendar
from core.models import (
    AssetClass,
    Candle,
    DepthLevel,
    Freshness,
    Instrument,
    OptionChainRow,
    OptionChainSnapshot,
    OptionType,
    Quote,
    Segment,
    Tick,
    Timeframe,
)
from core.time import IST, ensure_utc, utcnow
from providers.base import (
    ConnectionState,
    MarketDataProvider,
    ProviderCapability,
    ProviderHealth,
    ProviderInfo,
)

TICK = Decimal("0.05")
_ORIGIN = date(2024, 1, 1)  # daily random walk starts here
_SUPPORTED = frozenset({Timeframe.M1, Timeframe.M5, Timeframe.M15, Timeframe.H1, Timeframe.D1})
_MINUTES_PER_SESSION = 375  # 09:15 → 15:30


def _q(x: float | Decimal) -> Decimal:
    """Quantise to the 0.05 tick, 2dp."""
    d = Decimal(str(x)) if not isinstance(x, Decimal) else x
    return (d / TICK).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * TICK


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _bs(spot: float, strike: float, t_years: float, iv: float, call: bool) -> tuple[float, float]:
    """Black-Scholes price and delta with zero rate. Returns (price, delta)."""
    if t_years <= 0 or iv <= 0:
        intrinsic = max(0.0, spot - strike) if call else max(0.0, strike - spot)
        return intrinsic, (1.0 if spot > strike else 0.0) if call else (
            -1.0 if spot < strike else 0.0
        )
    d1 = (math.log(spot / strike) + 0.5 * iv * iv * t_years) / (iv * math.sqrt(t_years))
    d2 = d1 - iv * math.sqrt(t_years)
    if call:
        return spot * _norm_cdf(d1) - strike * _norm_cdf(d2), _norm_cdf(d1)
    return strike * _norm_cdf(-d2) - spot * _norm_cdf(-d1), _norm_cdf(d1) - 1.0


def _next_thursday(d: date) -> date:
    days = (3 - d.weekday()) % 7
    return d + timedelta(days=days or 7)


class FakeMarketDataProvider(MarketDataProvider):
    def __init__(
        self,
        seed: int = 42,
        tick_interval: float = 1.0,
        today: date | None = None,
    ) -> None:
        self._seed = seed
        self._tick_interval = tick_interval
        self._today = today or utcnow().astimezone(IST).date()
        self._cal = nse_calendar()
        self._state = ConnectionState.DISCONNECTED
        self._last_message_at: datetime | None = None
        self._instruments = self._build_universe()
        self._by_id = {i.instrument_id: i for i in self._instruments}
        # Optional canonical-id binding: db_id -> internal id, so callers may use DB ids.
        self._alias: dict[int, int] = {}
        self._reverse: dict[int, int] = {}
        # base price and daily volatility per instrument
        self._base: dict[int, float] = {}
        self._vol: dict[int, float] = {}
        for ins in self._instruments:
            self._base[ins.instrument_id], self._vol[ins.instrument_id] = self._params_for(ins)
        self._day_open_cache: dict[int, dict[date, float]] = {}
        self._live: dict[int, float] = {}
        self._live_rng = random.Random(seed ^ 0xBEEF)  # noqa: S311 - not security
        self._session_volume: dict[int, int] = {}

    # ------------------------------------------------------------------ universe
    def _build_universe(self) -> list[Instrument]:
        expiry = _next_thursday(self._today)
        tick = TICK
        base: list[Instrument] = [
            Instrument(
                instrument_id=1,
                exchange="NSE",
                segment=Segment.INDEX,
                asset_class=AssetClass.INDEX,
                symbol="NIFTY",
                name="Nifty 50",
                lot_size=1,
                tick_size=tick,
            ),
            Instrument(
                instrument_id=2,
                exchange="NSE",
                segment=Segment.INDEX,
                asset_class=AssetClass.INDEX,
                symbol="BANKNIFTY",
                name="Nifty Bank",
                lot_size=1,
                tick_size=tick,
            ),
            Instrument(
                instrument_id=3,
                exchange="NSE",
                segment=Segment.INDEX,
                asset_class=AssetClass.INDEX,
                symbol="INDIAVIX",
                name="India VIX",
                lot_size=1,
                tick_size=Decimal("0.0025"),
            ),
        ]
        stocks = [
            (4, "RELIANCE", "Reliance Industries", "INE002A01018"),
            (5, "TCS", "Tata Consultancy Services", "INE467B01029"),
            (6, "HDFCBANK", "HDFC Bank", "INE040A01034"),
            (7, "INFY", "Infosys", "INE009A01021"),
            (8, "SBIN", "State Bank of India", "INE062A01020"),
        ]
        for iid, sym, name, isin in stocks:
            base.append(
                Instrument(
                    instrument_id=iid,
                    exchange="NSE",
                    segment=Segment.EQUITY,
                    asset_class=AssetClass.STOCK,
                    symbol=sym,
                    name=name,
                    isin=isin,
                    lot_size=1,
                    tick_size=tick,
                )
            )
        exp_tag = expiry.strftime("%d%b%y").upper()
        base.append(
            Instrument(
                instrument_id=9,
                exchange="NSE",
                segment=Segment.FUTURES,
                asset_class=AssetClass.FUTURE,
                symbol=f"NIFTY{exp_tag}FUT",
                name="Nifty 50 Future",
                underlying_symbol="NIFTY",
                expiry=expiry,
                lot_size=75,
                tick_size=tick,
            )
        )
        atm = 24000
        iid = 10
        for strike in (atm - 50, atm, atm + 50):
            for ot in (OptionType.CE, OptionType.PE):
                base.append(
                    Instrument(
                        instrument_id=iid,
                        exchange="NSE",
                        segment=Segment.OPTIONS,
                        asset_class=AssetClass.OPTION,
                        symbol=f"NIFTY{exp_tag}{strike}{ot.value}",
                        name=f"Nifty 50 {strike} {ot.value}",
                        underlying_symbol="NIFTY",
                        expiry=expiry,
                        strike=Decimal(strike),
                        option_type=ot,
                        lot_size=75,
                        tick_size=tick,
                    )
                )
                iid += 1
        return base

    @staticmethod
    def _params_for(ins: Instrument) -> tuple[float, float]:
        table: dict[str, tuple[float, float]] = {
            "NIFTY": (24000.0, 0.010),
            "BANKNIFTY": (52000.0, 0.013),
            "INDIAVIX": (14.0, 0.05),
            "RELIANCE": (2900.0, 0.015),
            "TCS": (4100.0, 0.014),
            "HDFCBANK": (1650.0, 0.014),
            "INFY": (1800.0, 0.016),
            "SBIN": (820.0, 0.018),
        }
        if ins.symbol in table:
            return table[ins.symbol]
        if ins.segment == Segment.FUTURES:
            return 24060.0, 0.010
        # options: rough premium, high vol
        assert ins.strike is not None and ins.option_type is not None
        spot = 24000.0
        price, _ = _bs(spot, float(ins.strike), 5 / 365, 0.15, ins.option_type == OptionType.CE)
        return max(price, 5.0), 0.25

    # ------------------------------------------------------------------ prices
    def _rng(self, *parts: int) -> random.Random:
        return random.Random(hash((self._seed, *parts)) & 0xFFFFFFFF)  # noqa: S311

    def _day_open(self, iid: int, d: date) -> float:
        cache = self._day_open_cache.setdefault(iid, {})
        if d in cache:
            return cache[d]
        price = self._base[iid]
        vol = self._vol[iid]
        cur = _ORIGIN
        last = _ORIGIN
        if cache:
            last = max(k for k in cache if k <= d) if any(k <= d for k in cache) else _ORIGIN
            price = cache.get(last, price)
            cur = last
        while cur < d:
            cur += timedelta(days=1)
            if self._cal.is_trading_day(cur):
                price *= math.exp(self._rng(iid, cur.toordinal()).gauss(0.0002, vol))
                cache[cur] = price
        cache.setdefault(d, price)
        return cache[d]

    def _minute_path(self, iid: int, d: date) -> list[float]:
        """375 minute closes for one session, starting at the day open."""
        rng = self._rng(iid, d.toordinal(), 1)
        vol_min = self._vol[iid] / math.sqrt(_MINUTES_PER_SESSION)
        p = self._day_open(iid, d)
        out: list[float] = []
        for _ in range(_MINUTES_PER_SESSION):
            p *= math.exp(rng.gauss(0.0, vol_min))
            out.append(p)
        return out

    def _minute_candles(self, iid: int, d: date) -> list[Candle]:
        bounds = self._cal.session_bounds_utc(d)
        if bounds is None:
            return []
        open_utc, _ = bounds
        path = self._minute_path(iid, d)
        rng = self._rng(iid, d.toordinal(), 2)
        prev = self._day_open(iid, d)
        now = utcnow()
        out: list[Candle] = []
        for k, close in enumerate(path):
            o = prev
            spread = abs(close - o) + o * 0.0004 * rng.random()
            hi = max(o, close) + spread * rng.random()
            lo = min(o, close) - spread * rng.random()
            vol = 0 if iid == 3 else int(rng.lognormvariate(10, 0.6))
            ts = open_utc + timedelta(minutes=k)
            out.append(
                Candle(
                    instrument_id=iid,
                    timeframe=Timeframe.M1,
                    ts=ts,
                    open=_q(o),
                    high=_q(hi),
                    low=_q(lo),
                    close=_q(close),
                    volume=vol,
                    provider_id="fake",
                    provider_ts=ts,
                    received_at=now,
                    is_demo=True,
                )
            )
            prev = close
        return out

    @staticmethod
    def _resample(bars: list[Candle], tf: Timeframe) -> list[Candle]:
        if tf == Timeframe.M1 or not bars:
            return bars
        if tf == Timeframe.D1:
            groups = [bars]
        else:
            dur = tf.duration
            assert dur is not None
            n = int(dur.total_seconds() // 60)
            groups = [bars[i : i + n] for i in range(0, len(bars), n)]
        out: list[Candle] = []
        for g in groups:
            out.append(
                Candle(
                    instrument_id=g[0].instrument_id,
                    timeframe=tf,
                    ts=g[0].ts,
                    open=g[0].open,
                    high=max(b.high for b in g),
                    low=min(b.low for b in g),
                    close=g[-1].close,
                    volume=sum(b.volume for b in g),
                    provider_id="fake",
                    provider_ts=g[0].ts,
                    received_at=g[0].received_at,
                    is_demo=True,
                    derived_from=Timeframe.M1,
                )
            )
        return out

    def _current_price(self, iid: int) -> float:
        if iid not in self._live:
            d = self._today
            while not self._cal.is_trading_day(d):
                d -= timedelta(days=1)
            self._live[iid] = self._minute_path(iid, d)[-1]
        return self._live[iid]

    def _step_live(self, iid: int) -> float:
        p = self._current_price(iid)
        vol_tick = self._vol[iid] / math.sqrt(_MINUTES_PER_SESSION * 20)
        p *= math.exp(self._live_rng.gauss(0.0, vol_tick))
        self._live[iid] = p
        return p

    # ------------------------------------------------------------------ interface
    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(
            code="fake",
            display_name="Demo data (fake)",
            capabilities=frozenset(
                {
                    ProviderCapability.LIVE_QUOTES,
                    ProviderCapability.LIVE_TICKS,
                    ProviderCapability.HISTORICAL_CANDLES,
                    ProviderCapability.OPTION_CHAIN,
                    ProviderCapability.INSTRUMENT_MASTER,
                }
            ),
            is_demo=True,
            supported_timeframes=_SUPPORTED,
        )

    async def connect(self) -> None:
        self._state = ConnectionState.CONNECTED
        self._last_message_at = utcnow()

    async def disconnect(self) -> None:
        self._state = ConnectionState.DISCONNECTED

    async def health(self) -> ProviderHealth:
        return ProviderHealth(
            code="fake",
            state=self._state,
            last_message_at=self._last_message_at,
            latency_ms=0.0 if self._state == ConnectionState.CONNECTED else None,
            message="demo data; not a real market feed",
        )

    async def fetch_instruments(self) -> Sequence[Instrument]:
        return list(self._instruments)

    def provider_token(self, instrument: Instrument) -> str:
        """Token stored in instrument_mappings for this provider: the symbol."""
        return instrument.symbol

    def bind_mapping(self, mapping: dict[int, str]) -> None:
        """Accept canonical DB ids: {db_instrument_id: provider_token(symbol)}. After this,
        every method accepts either internal or DB ids and emits DB ids."""
        by_symbol = {i.symbol: i.instrument_id for i in self._instruments}
        self._alias = {db_id: by_symbol[tok] for db_id, tok in mapping.items() if tok in by_symbol}
        self._reverse = {v: k for k, v in self._alias.items()}

    def _internal(self, instrument_id: int) -> int:
        return self._alias.get(instrument_id, instrument_id)

    def _external(self, internal_id: int) -> int:
        return self._reverse.get(internal_id, internal_id)

    async def get_quotes(self, instrument_ids: Sequence[int]) -> Sequence[Quote]:
        quotes = await self._get_quotes_internal([self._internal(i) for i in instrument_ids])
        return [
            q.model_copy(update={"instrument_id": self._external(q.instrument_id)}) for q in quotes
        ]

    async def _get_quotes_internal(self, instrument_ids: Sequence[int]) -> Sequence[Quote]:
        now = utcnow()
        out: list[Quote] = []
        for iid in instrument_ids:
            if iid not in self._by_id:
                continue
            p = self._current_price(iid)
            ltp = _q(p)
            half = TICK if iid != 3 else Decimal("0")
            prev_day = self._cal.previous_trading_day(self._today)
            out.append(
                Quote(
                    instrument_id=iid,
                    ts=now,
                    ltp=ltp,
                    bid=ltp - half,
                    ask=ltp + half,
                    bid_qty=75,
                    ask_qty=75,
                    volume=self._session_volume.get(iid, 0),
                    prev_close=_q(self._day_open(iid, self._today)),
                    open=_q(self._day_open(iid, self._today)),
                    freshness=Freshness.DEMO,
                    provider_id="fake",
                    provider_ts=now,
                    received_at=now,
                    is_demo=True,
                )
            )
            _ = prev_day
        return out

    async def get_candles(
        self, instrument_id: int, timeframe: Timeframe, start: datetime, end: datetime
    ) -> Sequence[Candle]:
        ext = instrument_id
        instrument_id = self._internal(instrument_id)
        if timeframe not in _SUPPORTED:
            raise ValueError(f"fake provider does not support timeframe {timeframe}")
        if instrument_id not in self._by_id:
            return []
        bars = await self._get_candles_internal(instrument_id, timeframe, start, end)
        if ext == instrument_id:
            return bars
        return [b.model_copy(update={"instrument_id": ext}) for b in bars]

    async def _get_candles_internal(
        self, instrument_id: int, timeframe: Timeframe, start: datetime, end: datetime
    ) -> Sequence[Candle]:
        start, end = ensure_utc(start), ensure_utc(end)
        d = start.astimezone(IST).date()
        last = end.astimezone(IST).date()
        out: list[Candle] = []
        while d <= last:
            if self._cal.is_trading_day(d):
                bars = self._resample(self._minute_candles(instrument_id, d), timeframe)
                out.extend(b for b in bars if start <= b.ts < end)
            d += timedelta(days=1)
        return out

    async def get_option_chain(
        self, underlying_instrument_id: int, expiry: datetime
    ) -> OptionChainSnapshot:
        ext = underlying_instrument_id
        snap = await self._get_option_chain_internal(self._internal(ext), expiry)
        if not self._alias:
            return snap
        rows = tuple(
            r.model_copy(update={"instrument_id": self._external(r.instrument_id)})
            for r in snap.rows
        )
        return snap.model_copy(update={"underlying_instrument_id": ext, "rows": rows})

    async def _get_option_chain_internal(
        self, underlying_instrument_id: int, expiry: datetime
    ) -> OptionChainSnapshot:
        expiry = ensure_utc(expiry)
        spot = self._current_price(underlying_instrument_id)
        now = utcnow()
        t_years = max((expiry - now).total_seconds(), 0.0) / (365 * 86400)
        rng = self._rng(underlying_instrument_id, expiry.toordinal(), 3)
        step = 50 if underlying_instrument_id == 1 else 100
        atm = round(spot / step) * step
        rows: list[OptionChainRow] = []
        for k in range(-5, 6):
            strike = atm + k * step
            for ot in (OptionType.CE, OptionType.PE):
                iv = 0.12 + 0.08 * rng.random() + 0.002 * abs(k)
                price, delta = _bs(spot, float(strike), t_years, iv, ot == OptionType.CE)
                ltp = _q(max(price, 0.05))
                ins = next(
                    (
                        i
                        for i in self._instruments
                        if i.strike == strike
                        and i.option_type == ot
                        and i.underlying_symbol == "NIFTY"
                    ),
                    None,
                )
                rows.append(
                    OptionChainRow(
                        instrument_id=ins.instrument_id if ins else 0,
                        strike=Decimal(strike),
                        option_type=ot,
                        ltp=ltp,
                        bid=max(ltp - TICK, Decimal("0.05")),
                        ask=ltp + TICK,
                        volume=int(rng.lognormvariate(11, 0.8)),
                        oi=int(rng.lognormvariate(13, 0.7)),
                        oi_change=int(rng.gauss(0, 50_000)),
                        iv=Decimal(str(round(iv * 100, 2))),
                        delta=Decimal(str(round(delta, 4))),
                    )
                )
        return OptionChainSnapshot(
            underlying_instrument_id=underlying_instrument_id,
            expiry=expiry,
            ts=now,
            underlying_price=_q(spot),
            rows=tuple(rows),
            provider_id="fake",
            provider_ts=now,
            received_at=now,
            is_demo=True,
        )

    async def stream_ticks(self, instrument_ids: Sequence[int]) -> AsyncIterator[Tick]:
        ids = [self._internal(i) for i in instrument_ids if self._internal(i) in self._by_id]
        while self._state == ConnectionState.CONNECTED:
            now = datetime.now(UTC)
            for iid in ids:
                p = _q(self._step_live(iid))
                qty = 0 if iid == 3 else int(self._live_rng.lognormvariate(4, 0.8))
                self._session_volume[iid] = self._session_volume.get(iid, 0) + qty
                self._last_message_at = now
                yield Tick(
                    instrument_id=self._external(iid),
                    ts=now,
                    ltp=p,
                    ltq=qty or None,
                    volume=self._session_volume[iid] or None,
                    bids=(DepthLevel(price=p - TICK, quantity=75, orders=3),),
                    asks=(DepthLevel(price=p + TICK, quantity=75, orders=2),),
                    provider_id="fake",
                    provider_ts=now,
                    received_at=now,
                    is_demo=True,
                )
            if self._tick_interval > 0:
                await asyncio.sleep(self._tick_interval)
            else:
                await asyncio.sleep(0)
