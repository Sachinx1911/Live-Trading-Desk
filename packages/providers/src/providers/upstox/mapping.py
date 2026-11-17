"""Pure functions: Upstox payloads → canonical models. No I/O."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

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
from core.time import IST, ensure_utc

PROVIDER_ID = "upstox"

INDEX_KEYS = {
    "NSE_INDEX|Nifty 50": "NIFTY",
    "NSE_INDEX|Nifty Bank": "BANKNIFTY",
    "NSE_INDEX|India VIX": "INDIAVIX",
    "NSE_INDEX|Nifty Fin Service": "FINNIFTY",
    "NSE_INDEX|NIFTY MID SELECT": "MIDCPNIFTY",
}

# Timeframe → (unit, interval) for the v3 historical API.
TF_UNIT: dict[Timeframe, tuple[str, int]] = {
    Timeframe.M1: ("minutes", 1),
    Timeframe.M5: ("minutes", 5),
    Timeframe.M15: ("minutes", 15),
    Timeframe.M30: ("minutes", 30),
    Timeframe.H1: ("hours", 1),
    Timeframe.D1: ("days", 1),
    Timeframe.W1: ("weeks", 1),
    Timeframe.MN1: ("months", 1),
}

# Max calendar days per historical request (documented Upstox limits, conservative).
HISTORICAL_LIMITS: dict[Timeframe, int] = {
    Timeframe.M1: 30,
    Timeframe.M5: 30,
    Timeframe.M15: 30,
    Timeframe.M30: 90,
    Timeframe.H1: 90,
    Timeframe.D1: 3650,
    Timeframe.W1: 36500,
    Timeframe.MN1: 36500,
}


def _dec(v: Any) -> Decimal:
    return Decimal(str(v))


def _dec_or_none(v: Any) -> Decimal | None:
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except Exception:
        return None


def _int_or_none(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def ms_to_utc(ms: int | str) -> datetime:
    return datetime.fromtimestamp(int(ms) / 1000, tz=UTC)


def expiry_from_ms(ms: int | str | None) -> date | None:
    """Upstox expiry is ms epoch at IST end-of-day; return the IST calendar date."""
    if ms in (None, "", 0):
        return None
    return ms_to_utc(int(ms)).astimezone(IST).date()


# ----------------------------------------------------------------------------- instruments
def map_instrument(rec: Mapping[str, Any], provisional_id: int) -> Instrument | None:
    """Map one NSE.json record. Returns None for segments/types we do not model."""
    segment = str(rec.get("segment", ""))
    itype = str(rec.get("instrument_type", "")).upper()
    key = str(rec.get("instrument_key", ""))
    tick = _dec_or_none(rec.get("tick_size")) or Decimal("0.05")
    lot = _int_or_none(rec.get("lot_size")) or 1
    if segment == "NSE_INDEX":
        symbol = INDEX_KEYS.get(key) or str(rec.get("trading_symbol") or rec.get("name") or "")
        symbol = symbol.replace(" ", "").upper()
        return Instrument(
            instrument_id=provisional_id,
            exchange="NSE",
            segment=Segment.INDEX,
            asset_class=AssetClass.INDEX,
            symbol=symbol,
            name=str(rec.get("name") or symbol),
            lot_size=1,
            tick_size=tick,
        )
    if segment == "NSE_EQ":
        if itype not in ("EQ", "", "EQUITY"):
            return None  # ETFs/bonds/etc. come later
        symbol = str(rec.get("trading_symbol") or "").upper()
        if not symbol:
            return None
        return Instrument(
            instrument_id=provisional_id,
            exchange="NSE",
            segment=Segment.EQUITY,
            asset_class=AssetClass.STOCK,
            symbol=symbol,
            name=str(rec.get("name") or symbol),
            isin=rec.get("isin"),
            lot_size=lot,
            tick_size=tick,
        )
    if segment == "NSE_FO":
        expiry = expiry_from_ms(rec.get("expiry"))
        underlying = str(rec.get("underlying_symbol") or rec.get("name") or "").upper()
        symbol = str(rec.get("trading_symbol") or "").upper().replace(" ", "")
        if itype == "FUT":
            return Instrument(
                instrument_id=provisional_id,
                exchange="NSE",
                segment=Segment.FUTURES,
                asset_class=AssetClass.FUTURE,
                symbol=symbol,
                name=str(rec.get("name") or symbol),
                underlying_symbol=underlying,
                expiry=expiry,
                lot_size=lot,
                tick_size=tick,
            )
        if itype in ("CE", "PE"):
            strike = _dec_or_none(rec.get("strike_price"))
            if strike is None:
                return None
            return Instrument(
                instrument_id=provisional_id,
                exchange="NSE",
                segment=Segment.OPTIONS,
                asset_class=AssetClass.OPTION,
                symbol=symbol,
                name=str(rec.get("name") or symbol),
                underlying_symbol=underlying,
                expiry=expiry,
                strike=strike,
                option_type=OptionType(itype),
                lot_size=lot,
                tick_size=tick,
            )
    return None


def map_instruments(
    records: Iterable[Mapping[str, Any]], start_id: int = 1_000_000
) -> tuple[list[Instrument], dict[int, str]]:
    """Return canonical instruments with provisional ids and the id → instrument_key map."""
    out: list[Instrument] = []
    keys: dict[int, str] = {}
    next_id = start_id
    for rec in records:
        inst = map_instrument(rec, next_id)
        if inst is None:
            continue
        out.append(inst)
        keys[next_id] = str(rec["instrument_key"])
        next_id += 1
    return out, keys


# ----------------------------------------------------------------------------- candles
def map_candles(
    body: Mapping[str, Any],
    instrument_id: int,
    timeframe: Timeframe,
    received_at: datetime,
) -> list[Candle]:
    rows = (body.get("data") or {}).get("candles") or []
    out: list[Candle] = []
    for row in rows:
        ts = datetime.fromisoformat(str(row[0]))
        out.append(
            Candle(
                instrument_id=instrument_id,
                timeframe=timeframe,
                ts=ensure_utc(ts),
                open=_dec(row[1]),
                high=_dec(row[2]),
                low=_dec(row[3]),
                close=_dec(row[4]),
                volume=int(row[5] or 0),
                oi=_int_or_none(row[6]) if len(row) > 6 else None,
                provider_id=PROVIDER_ID,
                provider_ts=ensure_utc(ts),
                received_at=received_at,
            )
        )
    out.sort(key=lambda c: c.ts)
    return out


def chunk_ranges(start: date, end: date, max_days: int) -> list[tuple[date, date]]:
    """Split [start, end] into inclusive chunks of at most `max_days` calendar days."""
    if end < start:
        return []
    chunks: list[tuple[date, date]] = []
    cur = start
    while cur <= end:
        stop = min(end, cur + timedelta(days=max_days - 1))
        chunks.append((cur, stop))
        cur = stop + timedelta(days=1)
    return chunks


# ----------------------------------------------------------------------------- quotes
def _parse_quote_ts(v: Any, fallback: datetime) -> datetime:
    if v is None:
        return fallback
    if isinstance(v, int | float) or (isinstance(v, str) and v.isdigit()):
        return ms_to_utc(int(v))
    try:
        return ensure_utc(datetime.fromisoformat(str(v)))
    except ValueError:
        return fallback


def map_quotes(
    body: Mapping[str, Any],
    id_by_key: Mapping[str, int],
    received_at: datetime,
) -> list[Quote]:
    data = body.get("data") or {}
    out: list[Quote] = []
    for q in data.values():
        key = str(q.get("instrument_token") or "")
        iid = id_by_key.get(key)
        if iid is None:
            continue
        depth = q.get("depth") or {}
        buy = depth.get("buy") or []
        sell = depth.get("sell") or []
        ohlc = q.get("ohlc") or {}
        ltp = _dec(q.get("last_price") or 0)
        net_change = _dec_or_none(q.get("net_change"))
        prev_close = _dec_or_none(ohlc.get("close")) if ohlc else None
        if prev_close is None and net_change is not None:
            prev_close = ltp - net_change
        out.append(
            Quote(
                instrument_id=iid,
                ts=_parse_quote_ts(q.get("last_trade_time") or q.get("timestamp"), received_at),
                ltp=ltp,
                bid=_dec_or_none(buy[0]["price"]) if buy else None,
                ask=_dec_or_none(sell[0]["price"]) if sell else None,
                bid_qty=_int_or_none(buy[0].get("quantity")) if buy else None,
                ask_qty=_int_or_none(sell[0].get("quantity")) if sell else None,
                volume=_int_or_none(q.get("volume")),
                oi=_int_or_none(q.get("oi")),
                open=_dec_or_none(ohlc.get("open")),
                high=_dec_or_none(ohlc.get("high")),
                low=_dec_or_none(ohlc.get("low")),
                prev_close=prev_close,
                freshness=Freshness.DELAYED,  # REST snapshot; collector re-grades
                provider_id=PROVIDER_ID,
                provider_ts=_parse_quote_ts(q.get("timestamp"), received_at),
                received_at=received_at,
            )
        )
    return out


# ----------------------------------------------------------------------------- option chain
def map_option_chain(
    body: Mapping[str, Any],
    underlying_instrument_id: int,
    expiry: datetime,
    id_by_key: Mapping[str, int],
    received_at: datetime,
) -> OptionChainSnapshot:
    rows: list[OptionChainRow] = []
    spot: Decimal | None = None
    for strike_rec in body.get("data") or []:
        strike = _dec(strike_rec.get("strike_price"))
        spot = spot or _dec_or_none(strike_rec.get("underlying_spot_price"))
        for side, otype in (
            ("call_options", OptionType.CE),
            ("put_options", OptionType.PE),
        ):
            leg = strike_rec.get(side) or {}
            key = str(leg.get("instrument_key") or "")
            iid = id_by_key.get(key, 0)
            md = leg.get("market_data") or {}
            g = leg.get("option_greeks") or {}
            oi = _int_or_none(md.get("oi"))
            prev_oi = _int_or_none(md.get("prev_oi"))
            rows.append(
                OptionChainRow(
                    instrument_id=iid,
                    strike=strike,
                    option_type=otype,
                    ltp=_dec_or_none(md.get("ltp")),
                    bid=_dec_or_none(md.get("bid_price")),
                    ask=_dec_or_none(md.get("ask_price")),
                    volume=_int_or_none(md.get("volume")),
                    oi=oi,
                    oi_change=(oi - prev_oi) if oi is not None and prev_oi is not None else None,
                    iv=_dec_or_none(g.get("iv")),
                    delta=_dec_or_none(g.get("delta")),
                    theta=_dec_or_none(g.get("theta")),
                    gamma=_dec_or_none(g.get("gamma")),
                    vega=_dec_or_none(g.get("vega")),
                )
            )
    return OptionChainSnapshot(
        underlying_instrument_id=underlying_instrument_id,
        expiry=ensure_utc(expiry),
        ts=received_at,
        underlying_price=spot,
        rows=tuple(rows),
        provider_id=PROVIDER_ID,
        provider_ts=None,
        received_at=received_at,
    )


# ----------------------------------------------------------------------------- feed
def _levels(
    quotes: Iterable[Any],
) -> tuple[tuple[DepthLevel, ...], tuple[DepthLevel, ...]]:
    bids: list[DepthLevel] = []
    asks: list[DepthLevel] = []
    for q in quotes:
        if q.bidP > 0 or q.bidQ > 0:
            bids.append(DepthLevel(price=_dec(q.bidP), quantity=int(q.bidQ)))
        if q.askP > 0 or q.askQ > 0:
            asks.append(DepthLevel(price=_dec(q.askP), quantity=int(q.askQ)))
    return tuple(bids), tuple(asks)


def map_feed_response(
    msg: Any,
    id_by_key: Mapping[str, int],
    received_at: datetime,
) -> list[Tick]:
    """Decode a `FeedResponse` protobuf message into canonical ticks."""
    ticks: list[Tick] = []
    current_ts = ms_to_utc(msg.currentTs) if msg.currentTs else received_at
    for key, feed in msg.feeds.items():
        iid = id_by_key.get(key)
        if iid is None:
            continue
        which = feed.WhichOneof("FeedUnion")
        ltpc = None
        bids: tuple[DepthLevel, ...] = ()
        asks: tuple[DepthLevel, ...] = ()
        volume: int | None = None
        oi: int | None = None
        if which == "ltpc":
            ltpc = feed.ltpc
        elif which == "fullFeed":
            ff_which = feed.fullFeed.WhichOneof("FullFeedUnion")
            if ff_which == "marketFF":
                m = feed.fullFeed.marketFF
                ltpc = m.ltpc
                bids, asks = _levels(m.marketLevel.bidAskQuote)
                volume = int(m.vtt) if m.vtt else None
                oi = int(m.oi) if m.oi else None
            elif ff_which == "indexFF":
                ltpc = feed.fullFeed.indexFF.ltpc
        elif which == "firstLevelWithGreeks":
            f = feed.firstLevelWithGreeks
            ltpc = f.ltpc
            bids, asks = _levels([f.firstDepth])
            volume = int(f.vtt) if f.vtt else None
            oi = int(f.oi) if f.oi else None
        if ltpc is None or ltpc.ltp <= 0:
            continue
        ts = ms_to_utc(ltpc.ltt) if ltpc.ltt else current_ts
        ticks.append(
            Tick(
                instrument_id=iid,
                ts=ts,
                ltp=_dec(ltpc.ltp),
                ltq=int(ltpc.ltq) if ltpc.ltq else None,
                volume=volume,
                oi=oi,
                bids=bids,
                asks=asks,
                provider_id=PROVIDER_ID,
                provider_ts=current_ts,
                received_at=received_at,
            )
        )
    return ticks
