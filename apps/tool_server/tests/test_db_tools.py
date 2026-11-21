"""DB-backed tool-server tests: contract per tool (empty data, demo data, closed market with a
real provider), auth refusals logged, secret scan, MCP end to end. Skipped without
TEST_DATABASE_URL_SYNC."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import fakeredis.aioredis
import httpx
import httpx2
import orjson
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from ts_support import FAKE_JWT_SECRET, FAKE_SECRETS_KEY, make_settings, needs_db

from core.db.models import AuditLog, ToolCall, ToolToken, User
from core.models import Candle, OptionChainRow, OptionChainSnapshot, OptionType, Quote, Timeframe
from core.secrets import SecretBox
from core.services.brokers import BrokerService
from core.services.tool_tokens import create_token, hash_token, lookup_token, revoke_token
from core.time import IST
from market_data.repo.candles import upsert_candles
from market_data.repo.chains import write_snapshot
from market_data.repo.instruments import get_by_symbol
from market_data.repo.quotes import cache_quote
from market_data.sync import sync_instrument_master
from protocols.catalogue import CATALOGUE
from providers.fake import FakeMarketDataProvider
from tool_server.main import create_app
from tool_server.service import ToolService

pytestmark = needs_db

# Thursday 19 Nov 2026, 10:30 IST (a session day) and Saturday 21 Nov 2026, 11:00 IST.
THU = datetime(2026, 11, 19, 10, 30, tzinfo=IST).astimezone(UTC)
SAT = datetime(2026, 11, 21, 11, 0, tzinfo=IST).astimezone(UTC)


def _clock(t: datetime) -> Callable[[], datetime]:
    return lambda: t


async def _user(db: AsyncSession) -> User:
    u = User(email=f"tools-{datetime.now(UTC).timestamp()}@example.com", password_hash="x")
    db.add(u)
    await db.flush()
    return u


def _service(
    sf: async_sessionmaker[AsyncSession], redis: Any, clock: datetime, **kw: Any
) -> ToolService:
    settings = make_settings(**kw)
    return ToolService(
        settings=settings,
        session_factory=sf,
        redis=redis,
        secret_box=SecretBox(FAKE_SECRETS_KEY),
        clock=_clock(clock),
    )


async def _token(db: AsyncSession, user: User, level: str = "green") -> str:
    new = await create_token(db, user_id=user.id, name="jarvis test", max_level=level)
    await db.commit()
    return new.plaintext


async def _seed_instruments(db: AsyncSession) -> dict[str, int]:
    await sync_instrument_master(FakeMarketDataProvider(seed=5, tick_interval=0), db)
    out = {}
    for s in ("NIFTY", "BANKNIFTY"):
        ins = await get_by_symbol(db, "NSE", s)
        assert ins is not None
        out[s] = ins.instrument_id
    await db.commit()
    return out


async def _calls(db: AsyncSession) -> list[ToolCall]:
    return list((await db.execute(select(ToolCall).order_by(ToolCall.id))).scalars())


def _assert_contract(name: str, result: dict[str, Any]) -> None:
    spec = CATALOGUE.get(name)
    assert spec is not None
    spec.output_model.model_validate(result)
    assert isinstance(result["source"], str) and result["source"]
    assert result["freshness"] in (
        "live",
        "delayed",
        "stale",
        "historical",
        "disconnected",
        "demo",
        "none",
    )
    assert isinstance(result["is_demo"], bool)
    assert result["summary"]


# ----------------------------------------------------------------------------- tokens + auth
async def test_token_lifecycle_stores_only_the_hash(db: AsyncSession) -> None:
    u = await _user(db)
    new = await create_token(db, user_id=u.id, name="jarvis", max_level="yellow")
    row = (await db.execute(select(ToolToken).where(ToolToken.id == new.row.id))).scalar_one()
    assert row.token_hash == hash_token(new.plaintext) and new.plaintext not in row.token_hash
    assert new.plaintext.startswith(row.prefix) and len(row.prefix) == 12
    assert (await lookup_token(db, new.plaintext)).status == "ok"
    assert (await lookup_token(db, new.plaintext + "x")).status == "invalid"
    assert (await lookup_token(db, None)).status == "missing"
    await revoke_token(db, row.id, u.id)
    found = await lookup_token(db, new.plaintext)
    assert found.status == "revoked" and found.token is not None


async def test_missing_invalid_revoked_tokens_refused_and_logged(
    db: AsyncSession, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    u = await _user(db)
    good = await _token(db, u)
    revoked = await _token(db, u)
    rid = (await lookup_token(db, revoked)).token.id  # type: ignore[union-attr]
    await revoke_token(db, rid, u.id)
    await db.commit()
    svc = _service(session_factory, fakeredis.aioredis.FakeRedis(decode_responses=True), SAT)
    app = create_app(svc, own_redis=False)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8100") as c:
        r1 = await c.post("/tools/owner_rules")
        r2 = await c.post("/tools/owner_rules", headers={"authorization": "Bearer ltd_nope"})
        r3 = await c.post("/tools/owner_rules", headers={"authorization": f"Bearer {revoked}"})
        r4 = await c.get("/tools", headers={"authorization": "Bearer ltd_nope"})
        r5 = await c.post("/tools/owner_rules", headers={"authorization": f"Bearer {good}"})
    assert [r.status_code for r in (r1, r2, r3, r4, r5)] == [401, 401, 401, 401, 200]
    assert r3.json()["error"]["message"] == "revoked token"
    rows = await _calls(db)
    assert [(c.tool, c.status) for c in rows] == [
        ("owner_rules", "refused"),
        ("owner_rules", "refused"),
        ("owner_rules", "refused"),
        ("tools/list", "refused"),
        ("owner_rules", "ok"),
    ]
    assert rows[2].token_id == rid and rows[0].token_id is None
    assert rows[4].result_meta["freshness"] == "none" and rows[4].duration_ms is not None
    tok = (await db.execute(select(ToolToken).where(ToolToken.id != rid))).scalars().all()
    assert any(t.last_used_at is not None for t in tok)


async def test_yellow_and_unknown_and_bad_args_logged(
    db: AsyncSession, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    u = await _user(db)
    tok = await _token(db, u, "yellow")
    svc = _service(session_factory, fakeredis.aioredis.FakeRedis(decode_responses=True), SAT)
    a = await svc.call(tok, "http", "kill_switch_on", {"scope": "global"})
    b = await svc.call(tok, "mcp", "place_order", {"qty": 1})
    c = await svc.call(tok, "http", "paper_pnl", {"period": "decade"})
    d = await svc.call(tok, "http", "paper_pnl", [1, 2])
    assert (a.http_status, a.code) == (403, "level_not_allowed")
    assert (b.http_status, b.code) == (404, "unknown_tool")
    assert (c.http_status, c.code) == (422, "bad_args")
    assert (d.http_status, d.code) == (422, "bad_args")
    rows = await _calls(db)
    assert [(r.tool, r.transport, r.status, r.level) for r in rows] == [
        ("kill_switch_on", "http", "refused", "yellow"),
        ("place_order", "mcp", "refused", None),
        ("paper_pnl", "http", "error", "green"),
        ("paper_pnl", "http", "error", "green"),
    ]
    assert rows[3].args == {"_invalid": "<list>"}


async def test_rate_limit_refuses_and_logs(
    db: AsyncSession, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    u = await _user(db)
    tok = await _token(db, u)
    svc = _service(
        session_factory,
        fakeredis.aioredis.FakeRedis(decode_responses=True),
        SAT,
        tool_server_rate_per_minute=2,
    )
    codes = [(await svc.call(tok, "http", "owner_rules", {})).code for _ in range(3)]
    assert codes == ["ok", "ok", "rate_limited"]
    assert [r.status for r in await _calls(db)] == ["ok", "ok", "refused"]


# ----------------------------------------------------------------------------- contracts
async def test_every_green_tool_answers_honestly_on_empty_data(
    db: AsyncSession, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    u = await _user(db)
    tok = await _token(db, u)
    await _seed_instruments(db)
    svc = _service(session_factory, fakeredis.aioredis.FakeRedis(decode_responses=True), SAT)
    for spec in CATALOGUE.callable_at("green"):
        if spec.writes:  # record_view refuses without a reference price: tested on its own
            continue
        out = await svc.call(tok, "http", spec.name, spec.example)
        assert out.status == "ok", (spec.name, out.code, out.message)
        assert out.result is not None
        _assert_contract(spec.name, out.result)
    quote = (await svc.call(tok, "http", "quote", {"symbols": ["NIFTY"]})).result
    assert quote is not None
    q = quote["quotes"][0]
    assert q["ltp"] is None and q["freshness"] == "disconnected" and q["is_demo"] is True
    assert "market closed" in q["reason"]
    for name, args in (
        ("candles", {"symbol": "NIFTY"}),
        ("option_chain", {"underlying": "NIFTY"}),
        ("breadth", {}),
        ("scanner_run", {"preset": "Top gainers"}),
    ):
        res = (await svc.call(tok, "http", name, args)).result
        assert res is not None and res["freshness"] == "none" and res["status"] == "no_data"


async def _seed_demo_market(db: AsyncSession, ids: dict[str, int], now: datetime) -> None:
    nifty = ids["NIFTY"]
    bars = []
    for i in range(30):
        ts = now - timedelta(minutes=5 * (30 - i))
        px = Decimal(24000 + i)
        bars.append(
            Candle(
                instrument_id=nifty,
                timeframe=Timeframe.M5,
                ts=ts,
                open=px,
                high=px + 5,
                low=px - 5,
                close=px + 1,
                volume=100,
                provider_id="fake",
                received_at=ts,
                is_demo=True,
            )
        )
    await upsert_candles(db, bars)
    expiry = datetime(2026, 11, 24, 15, 30, tzinfo=IST).astimezone(UTC)
    for minutes, oi_shift in ((70, 0), (10, 500)):
        ts = now - timedelta(minutes=minutes)
        rows = []
        for k, strike in enumerate(range(23800, 24300, 50)):
            for side in (OptionType.CE, OptionType.PE):
                rows.append(
                    OptionChainRow(
                        instrument_id=900000 + k * 2 + (side == OptionType.PE),
                        strike=Decimal(strike),
                        option_type=side,
                        ltp=Decimal(100),
                        oi=10_000 + oi_shift + (2000 if side == OptionType.PE else 0),
                        iv=Decimal("12.5"),
                        delta=Decimal("0.5") if side == OptionType.CE else Decimal("-0.5"),
                    )
                )
        await write_snapshot(
            db,
            OptionChainSnapshot(
                underlying_instrument_id=nifty,
                expiry=expiry,
                ts=ts,
                underlying_price=Decimal(24010),
                rows=tuple(rows),
                provider_id="fake",
                received_at=ts,
                is_demo=True,
            ),
        )
    await db.commit()


async def test_demo_data_is_labelled_demo(
    db: AsyncSession, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    u = await _user(db)
    tok = await _token(db, u)
    ids = await _seed_instruments(db)
    await _seed_demo_market(db, ids, THU)
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    await cache_quote(
        redis,
        Quote(
            instrument_id=ids["NIFTY"],
            ts=THU - timedelta(seconds=1),
            ltp=Decimal("24011.5"),
            prev_close=Decimal(24000),
            provider_id="fake",
            received_at=THU,
            is_demo=True,
        ),
    )
    svc = _service(session_factory, redis, THU)
    checks = {
        "quote": {"symbols": ["NIFTY"]},
        "candles": {"symbol": "NIFTY", "timeframe": "5m", "limit": 10},
        "option_chain": {"underlying": "NIFTY", "strikes_around_atm": 2},
        "greeks": {"underlying": "NIFTY", "strikes_around_atm": 1},
        "oi_change": {"underlying": "NIFTY", "start": "09:15", "end": "10:30"},
        "pcr": {"symbols": ["NIFTY"]},
    }
    for name, args in checks.items():
        out = await svc.call(tok, "mcp", name, args)
        assert out.status == "ok", (name, out.message)
        res = out.result
        assert res is not None
        _assert_contract(name, res)
        assert res["freshness"] == "demo" and res["is_demo"] is True, (name, res["freshness"])
    chain = (await svc.call(tok, "http", "option_chain", checks["option_chain"])).result
    assert chain is not None and chain["atm_strike"] == "24000"
    assert {r["strike"] for r in chain["rows"]} == {"23900", "23950", "24000", "24050", "24100"}
    oi = (await svc.call(tok, "http", "oi_change", checks["oi_change"])).result
    assert oi is not None and oi["call_oi_change_total"] == 500 * 10
    candles = (await svc.call(tok, "http", "candles", checks["candles"])).result
    assert candles is not None and len(candles["candles"]) == 10


async def test_real_provider_closed_market_is_disconnected_not_live(
    db: AsyncSession, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    u = await _user(db)
    tok = await _token(db, u)
    await _seed_instruments(db)
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    svc = _service(session_factory, redis, SAT, default_market_data_provider="upstox")
    res = (await svc.call(tok, "http", "quote", {"symbols": ["NIFTY", "NOPE"]})).result
    assert res is not None
    assert res["freshness"] == "disconnected" and res["is_demo"] is False
    rows = {r["symbol"]: r for r in res["quotes"]}
    assert rows["NIFTY"]["ltp"] is None and "market closed" in rows["NIFTY"]["reason"]
    assert "collector missing" in rows["NIFTY"]["reason"]
    assert rows["NOPE"]["status"] == "unknown symbol"


# ----------------------------------------------------------------------------- secrets
async def test_no_response_or_log_row_contains_a_secret(
    db: AsyncSession, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    u = await _user(db)
    tok = await _token(db, u)
    await _seed_instruments(db)
    box = SecretBox(FAKE_SECRETS_KEY)
    settings = make_settings()
    brokers = BrokerService(db, settings, box)
    api_key, api_secret, access = "UPSTOX-KEY-9f8e7d", "UPSTOX-SECRET-1a2b3c", "ACCESS-TOKEN-zz99"
    acct = await brokers.upsert_account(
        u.id, "upstox", client_code="AB1234", api_key=api_key, api_secret=api_secret
    )
    sess = await brokers.store_session(acct, access, SAT + timedelta(hours=8))
    await db.commit()
    secrets = [
        api_key,
        api_secret,
        access,
        FAKE_SECRETS_KEY,
        FAKE_JWT_SECRET,
        tok,
        hash_token(tok),
        acct.api_key_enc.decode() if acct.api_key_enc else "x" * 40,
        sess.access_token_enc.decode(),
    ]
    svc = _service(session_factory, fakeredis.aioredis.FakeRedis(decode_responses=True), SAT)
    app = create_app(svc, own_redis=False)
    texts: list[str] = []
    hdr = {"authorization": f"Bearer {tok}"}
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8100") as c:
        texts.append((await c.get("/tools", headers=hdr)).text)
        for spec in CATALOGUE.all():
            texts.append((await c.post(f"/tools/{spec.name}", json=spec.example, headers=hdr)).text)
        # Callers that send secrets in arguments do not get them stored or echoed back.
        hostile = {
            "symbols": [tok, FAKE_SECRETS_KEY[:30]],
            "token": tok,
            "api_secret": api_secret,
            "note": f"key {FAKE_SECRETS_KEY} jwt {FAKE_JWT_SECRET}",
        }
        texts.append((await c.post("/tools/quote", json=hostile, headers=hdr)).text)
        texts.append((await c.post("/tools/quote", json={"symbols": [tok]}, headers=hdr)).text)
        texts.append((await c.post(f"/tools/{tok}", json={}, headers=hdr)).text)
    rows = await _calls(db)
    texts.extend(
        orjson.dumps(
            {"tool": r.tool, "args": r.args, "error": r.error, "meta": r.result_meta}
        ).decode()
        for r in rows
    )
    audit = (await db.execute(select(AuditLog))).scalars().all()
    texts.extend(orjson.dumps({"a": a.after, "b": a.before}, default=str).decode() for a in audit)
    blob = "\n".join(texts)
    assert len(rows) >= len(CATALOGUE.all()) + 3
    for s in secrets:
        assert s not in blob, "a secret leaked into a tool response or log row"
    assert "broker_sessions" in {r.tool for r in rows}


# ----------------------------------------------------------------------------- MCP end to end
async def test_mcp_lists_the_same_tools_and_calls_through_the_same_path(
    db: AsyncSession, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    u = await _user(db)
    tok = await _token(db, u)
    svc = _service(session_factory, fakeredis.aioredis.FakeRedis(decode_responses=True), SAT)
    app = create_app(svc, own_redis=False)
    async with app.router.lifespan_context(app):
        transport = httpx2.ASGITransport(app=app)
        http = httpx2.AsyncClient(
            transport=transport,
            base_url="http://127.0.0.1:8100",
            headers={"authorization": f"Bearer {tok}"},
        )
        async with (
            http,
            Client(streamable_http_client("http://127.0.0.1:8100/mcp", http_client=http)) as mc,
        ):
            listed = await mc.list_tools()
            res = await mc.call_tool("owner_rules", {})
            bad = await mc.call_tool("kill_switch_on", {"scope": "global"})
        noauth = httpx2.AsyncClient(transport=transport, base_url="http://127.0.0.1:8100")
        async with noauth:
            r = await noauth.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
    names = {t.name for t in listed.tools}
    assert names == {t.name for t in CATALOGUE.callable_at("green")}
    by = {t.name: t for t in listed.tools}
    assert by["quote"].input_schema == CATALOGUE.get("quote").input_schema()  # type: ignore[union-attr]
    assert res.is_error is False and res.structured_content is not None
    assert res.structured_content["freshness"] == "none"
    assert bad.is_error is True
    assert r.status_code == 401
    rows = await _calls(db)
    assert ("owner_rules", "mcp", "ok") in {(c.tool, c.transport, c.status) for c in rows}
    assert ("kill_switch_on", "mcp", "refused") in {(c.tool, c.transport, c.status) for c in rows}
    assert ("mcp/connect", "mcp", "refused") in {(c.tool, c.transport, c.status) for c in rows}


async def test_record_view_takes_our_price_and_refuses_without_one(
    db: AsyncSession, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Stage 4.6 hook: the view is stored with the platform's own reference price and the
    server-set caller; with no price at all nothing is stored and the refusal is logged."""
    from core.db.models import AiObservation

    u = await _user(db)
    tok = await _token(db, u)
    ids = await _seed_instruments(db)
    args = {"symbol": "NIFTY", "direction": "up", "horizon_days": 5, "confidence": "0.65"}

    empty = _service(session_factory, fakeredis.aioredis.FakeRedis(decode_responses=True), SAT)
    refused = await empty.call(tok, "http", "record_view", args)
    assert refused.status == "error" and "no_reference_price" in (refused.message or "")
    assert (await db.execute(select(AiObservation))).scalars().first() is None

    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    await cache_quote(
        redis,
        Quote(
            instrument_id=ids["NIFTY"],
            ts=THU - timedelta(seconds=1),
            ltp=Decimal("24011.5"),
            prev_close=Decimal(24000),
            provider_id="fake",
            received_at=THU,
            is_demo=True,
        ),
    )
    svc = _service(session_factory, redis, THU)
    out = await svc.call(tok, "http", "record_view", {**args, "mode": "friday"})
    assert out.status == "ok", (out.code, out.message)
    assert out.result is not None
    _assert_contract("record_view", out.result)
    assert out.result["is_demo"] is True and out.result["freshness"] in ("demo", "historical")
    obs = (await db.execute(select(AiObservation))).scalars().one()
    assert obs.caller == "jarvis" and obs.mode == "friday"
    assert obs.ref_price == Decimal("24011.5")

    sneaky = await svc.call(tok, "http", "record_view", {**args, "ref_price": "1"})
    assert sneaky.status != "ok"  # a caller can never supply the reference price
