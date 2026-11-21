"""Database-backed protocol and alert tests (skipped without TEST_DATABASE_URL_SYNC)."""

from __future__ import annotations

import os
from datetime import timedelta
from decimal import Decimal
from typing import Any

import fakeredis.aioredis
import orjson
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import (
    Alert,
    AuditLog,
    KillSwitchEvent,
    PaperAccount,
    PaperPosition,
    Protocol,
    ProtocolRun,
    Strategy,
    StrategyActivation,
    StrategyVersion,
    User,
)
from core.db.models._enums import (
    ActivationStatus,
    CreatedBy,
    StrategyCategory,
    StrategyOrigin,
    StrategyVersionStatus,
)
from core.models import ProductType, TradingMode
from core.notify.telegram import NullNotifier
from core.settings import Settings
from core.time import utcnow
from market_data.sync import sync_instrument_master
from protocols.alert_store import deliver, pending_alerts, record_alert, store_alerts
from protocols.alerts import AlertCandidate
from protocols.builtin import BUILTINS
from protocols.context import ActionContext
from protocols.service import (
    ProtocolError,
    cancel_run,
    confirm_run,
    create_run,
    execute_run,
    get_protocol,
    seed_builtins,
)
from providers.fake import FakeMarketDataProvider

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL_SYNC"), reason="TEST_DATABASE_URL_SYNC not set"
)

SETTINGS = Settings(_env_file=None)  # type: ignore[call-arg]


class Recorder:
    def __init__(self, ok: bool = True) -> None:
        self.sent: list[tuple[str, str]] = []
        self.ok = ok

    async def send(self, text: str, *, level: str = "info") -> bool:
        self.sent.append((level, text))
        return self.ok


async def _user(db: AsyncSession) -> User:
    u = User(email=f"proto-{utcnow().timestamp()}@example.com", password_hash="x")
    db.add(u)
    await db.flush()
    return u


async def _paper_setup(db: AsyncSession, user: User) -> tuple[PaperAccount, StrategyActivation]:
    ids = (await sync_instrument_master(FakeMarketDataProvider(seed=5, tick_interval=0), db)).id_map
    acct = PaperAccount(
        user_id=user.id,
        name="P",
        initial_capital=Decimal(100000),
        cash=Decimal(100000),
        equity_hwm=Decimal(100000),
    )
    db.add(acct)
    s = Strategy(
        user_id=user.id,
        name="s",
        category=StrategyCategory.TREND,
        origin=StrategyOrigin.USER_VISUAL,
    )
    db.add(s)
    await db.flush()
    v = StrategyVersion(
        strategy_id=s.id,
        version_no=1,
        status=StrategyVersionStatus.PAPER,
        dsl={},
        dsl_schema_version="1.0",
        dsl_hash="h",
        created_by=CreatedBy.USER,
    )
    db.add(v)
    await db.flush()
    act = StrategyActivation(
        version_id=v.id,
        trading_mode=TradingMode.PAPER,
        paper_account_id=acct.id,
        instrument_id=ids[1],
        params_override={},
        status=ActivationStatus.ACTIVE,
        activated_by=user.id,
    )
    db.add(act)
    await db.flush()
    db.add(
        PaperPosition(
            paper_account_id=acct.id,
            instrument_id=ids[1],
            product=ProductType.INTRADAY,
            activation_id=act.id,
            quantity=50,
            avg_price=Decimal("24000"),
            opened_at=utcnow(),
        )
    )
    await db.flush()
    return acct, act


def _ctx_factory(db: AsyncSession, redis: Any, notifier: Any = None) -> Any:
    def make(run: ProtocolRun) -> ActionContext:
        return ActionContext(
            db=db,
            redis=redis,
            settings=SETTINGS,
            notifier=notifier or NullNotifier(),
            user_id=run.user_id,
        )

    return make


async def test_seed_builtins_idempotent_and_bumps_version(db: AsyncSession) -> None:
    first = await seed_builtins(db)
    assert set(first) == {p.code for p in BUILTINS}
    again = await seed_builtins(db)
    assert set(again.values()) == {"unchanged"}
    p = await get_protocol(db, "review")
    assert p is not None and p.is_builtin and p.version >= 1
    v0 = p.version
    p.steps = [{"tool": "paper_status", "args": {}, "on_error": "stop"}]
    await db.flush()
    out = await seed_builtins(db)
    assert out["review"] == f"updated to v{v0 + 1}"
    await db.refresh(p)
    assert [s["tool"] for s in p.steps] == ["paper_status", "recent_alerts"]


async def test_confirm_flow_and_cancel(db: AsyncSession) -> None:
    await seed_builtins(db)
    u = await _user(db)
    p = await get_protocol(db, "shutdown")
    assert p is not None and p.confirm_required
    run = await create_run(db, p, user_id=u.id, trigger="button")
    assert run.status == "awaiting_confirmation"
    assert [s["status"] for s in run.steps] == ["pending"] * 3
    redis = fakeredis.aioredis.FakeRedis()
    assert await execute_run(db, run.id, _ctx_factory(db, redis)) is None  # not confirmed
    await confirm_run(db, run)
    assert run.status == "running"
    with pytest.raises(ProtocolError):
        await confirm_run(db, run)
    await cancel_run(db, run, "changed my mind")
    assert run.status == "cancelled"
    assert await execute_run(db, run.id, _ctx_factory(db, redis)) is None
    with pytest.raises(ProtocolError):
        await cancel_run(db, run)


async def test_shutdown_stops_strategies_and_reports_trader_down(db: AsyncSession) -> None:
    await seed_builtins(db)
    u = await _user(db)
    acct, act = await _paper_setup(db, u)
    p = await get_protocol(db, "shutdown")
    assert p is not None
    run = await create_run(db, p, user_id=u.id, trigger="api")
    await confirm_run(db, run)
    await db.flush()
    redis = fakeredis.aioredis.FakeRedis()  # no trader:health -> trader not running
    out = await execute_run(db, run.id, _ctx_factory(db, redis))
    assert out is not None
    assert [s["status"] for s in out.steps] == ["succeeded", "failed", "succeeded"]
    assert out.status == "partial"
    assert "paper trader is missing" in out.steps[1]["error"]
    await db.refresh(act)
    assert act.status == ActivationStatus.STOPPED and act.stop_reason.endswith("(flatten)")
    stored = await db.get(ProtocolRun, run.id)
    assert stored is not None
    await db.refresh(stored)
    assert stored.status == "partial" and stored.finished_at is not None
    status = out.steps[2]["result"]["accounts"][0]
    assert status["id"] == acct.id and len(status["open_positions"]) == 1
    audits = (
        (await db.execute(select(AuditLog.action).where(AuditLog.entity_id == str(act.id))))
        .scalars()
        .all()
    )
    assert "paper.activation.stop" in audits


async def test_close_positions_with_trader_running(db: AsyncSession) -> None:
    await seed_builtins(db)
    u = await _user(db)
    _, act = await _paper_setup(db, u)
    redis = fakeredis.aioredis.FakeRedis()
    await redis.set("trader:health", orjson.dumps({"updated_at": utcnow().isoformat()}))
    p = Protocol(
        code=f"close_only_{u.id}",
        name="close",
        steps=[{"tool": "close_paper_positions", "args": {}, "on_error": "stop"}],
        user_id=u.id,
    )
    db.add(p)
    await db.flush()
    run = await create_run(db, p, user_id=u.id, trigger="api")
    out = await execute_run(db, run.id, _ctx_factory(db, redis))
    assert out is not None and out.status == "succeeded"
    rows = out.steps[0]["result"]["positions"]
    assert [r["outcome"] for r in rows] == ["flatten_requested"]
    assert "fills are reported by the trader" in out.steps[0]["result"]["summary"]
    await db.refresh(act)
    assert act.status == ActivationStatus.STOPPED


async def test_clean_slate_engages_kill_switch_immediately(db: AsyncSession) -> None:
    await seed_builtins(db)
    u = await _user(db)
    p = await get_protocol(db, "clean_slate")
    assert p is not None and not p.confirm_required
    run = await create_run(db, p, user_id=u.id, trigger="button")
    assert run.status == "running"
    redis = fakeredis.aioredis.FakeRedis()
    rec = Recorder()
    out = await execute_run(db, run.id, _ctx_factory(db, redis, rec))
    assert out is not None and out.status == "succeeded"
    assert await redis.exists("kill:global") == 1
    ev = (await db.execute(select(KillSwitchEvent))).scalars().all()
    assert any(e.reason == "protocol: clean slate" for e in ev)
    assert rec.sent and rec.sent[0][0] == "critical"
    # second run: already on, nothing re-written
    run2 = await create_run(db, p, user_id=u.id, trigger="button")
    out2 = await execute_run(db, run2.id, _ctx_factory(db, redis, rec))
    assert out2 is not None and out2.steps[0]["result"]["already_active"] is True


async def test_health_and_market_open_runs_report_missing_data_honestly(db: AsyncSession) -> None:
    await seed_builtins(db)
    u = await _user(db)
    redis = fakeredis.aioredis.FakeRedis()
    for code in ("health_check", "market_open"):
        p = await get_protocol(db, code)
        assert p is not None
        run = await create_run(db, p, user_id=u.id, trigger="api")
        out = await execute_run(db, run.id, _ctx_factory(db, redis))
        assert out is not None
        hc = out.steps[0]["result"]
        assert hc["db"]["status"] == "ok" and hc["redis"]["status"] == "ok"
        assert hc["collector"]["status"] == "missing"
        assert hc["worker"]["status"] == "missing"
        assert hc["status"] == "degraded"  # worker heartbeat missing
    assert out.status == "succeeded"
    by_tool = {s["tool"]: s["result"] for s in out.steps}
    assert (
        by_tool["todays_events"]["summary"] in ("no events stored for today",)
        or by_tool["todays_events"]["events"]
    )
    for row in by_tool["pcr_now"]["pcr"]:
        assert row["pcr"] is None or row["source"]


async def test_alert_store_dedup_and_delivery(db: AsyncSession) -> None:
    now = utcnow()
    w = timedelta(minutes=30)
    key = f"test:{now.timestamp()}"
    c = AlertCandidate("feed_stale", "warning", "t", "m", key, {"x": Decimal("1.5")})
    first = await store_alerts(db, [c, c], now=now, window=w)
    assert len(first) == 1 and first[0].data == {"x": "1.5"}
    assert await store_alerts(db, [c], now=now + timedelta(minutes=10), window=w) == []
    later = await store_alerts(db, [c], now=now + timedelta(minutes=31), window=w)
    assert len(later) == 1
    rec = Recorder(ok=False)
    counts = await deliver(later, rec, configured=True)
    assert counts["failed"] == 1 and later[0].delivered["telegram"] == "failed"
    counts = await deliver(first, rec, configured=False)
    assert counts["skipped"] == 1
    pend_key = f"rule_block:{now.timestamp()}"
    a = await record_alert(
        db, AlertCandidate("rule_block", "warning", "t", "m", pend_key), now=now, window=w
    )
    assert a is not None and a.delivered["telegram"] == "pending"
    pend = await pending_alerts(db)
    assert any(x.id == a.id for x in pend)
    assert (
        await record_alert(
            db, AlertCandidate("rule_block", "warning", "t", "m", pend_key), now=now, window=w
        )
        is None
    )
    n = (await db.execute(select(Alert).where(Alert.dedup_key == pend_key))).scalars().all()
    assert len(n) == 1
