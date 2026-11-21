"""Replay session semantics on a synthetic candle set (no DB)."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from api.replay.manager import ReplayManager
from api.replay.session import ReplaySession
from core.calendar import nse_calendar
from core.models import Candle, Segment, Timeframe
from risk.limits import InstrumentMeta
from strategy.dsl.examples import load_example
from strategy.dsl.schema import StrategyDocument

CAL = nse_calendar()
DAYS = [date(2026, 11, 16), date(2026, 11, 17), date(2026, 11, 18)]  # Mon-Wed


def _day(d: date, base: float) -> list[Candle]:
    start, end = CAL.session_bounds_utc(d)  # type: ignore[misc]
    out: list[Candle] = []
    ts, i = start, 0
    while ts < end:
        px = base + (i % 7) * 2 - 6  # small deterministic wobble
        out.append(
            Candle(
                instrument_id=22,
                timeframe=Timeframe.M1,
                ts=ts,
                open=Decimal(px),
                high=Decimal(px + 3),
                low=Decimal(px - 3),
                close=Decimal(px + 1),
                volume=100,
                provider_id="fake",
                received_at=ts,
                is_demo=True,
            )
        )
        ts += timedelta(minutes=1)
        i += 1
    return out


WARM = _day(DAYS[0], 100) + _day(DAYS[1], 102)
TODAY = _day(DAYS[2], 104)
META = InstrumentMeta(instrument_id=22, symbol="NIFTY", segment=Segment.INDEX, lot_size=1)


def _strategy() -> StrategyDocument:
    d = load_example("ema_rsi_nifty")
    d["timeframe"] = "1m"
    d["entry"] = {
        "long": {
            "kind": "compare",
            "left": {"kind": "price", "field": "close"},
            "op": "gt",
            "right": {"kind": "const", "value": 0},
        }
    }
    d["exit"] = {"long": None, "time_exit_bars": 3}
    d["max_trades_per_day"] = 3
    d["session"]["trade_start"] = "09:16"
    return StrategyDocument.model_validate(d)


def _session(seed: int = 7, strategy: bool = True) -> ReplaySession:
    return ReplaySession(
        user_id=1,
        instrument_id=22,
        day=DAYS[2],
        timeframe=Timeframe.M1,
        candles_1m=TODAY,
        warmup_1m=WARM if strategy else (),
        strategy=_strategy() if strategy else None,
        strategy_version_id=1 if strategy else None,
        meta=META if strategy else None,
        speed=600,
        seed=seed,
        calendar=CAL,
    )


async def _drain(q: asyncio.Queue) -> list[dict]:  # type: ignore[type-arg]
    out = []
    while not q.empty():
        out.append(q.get_nowait())
    return out


def _strip(fills: list[dict]) -> list[dict]:  # type: ignore[type-arg]
    """Order ids are random uuids; everything else must be reproducible."""
    return [{k: v for k, v in f.items() if k != "order_id"} for f in fills]


def test_step_and_event_order() -> None:
    async def run() -> None:
        s = _session(strategy=False)
        q = s.subscribe()
        assert (await _drain(q))[0]["type"] == "state"
        st = await s.step(1)
        assert st["cursor"] == 1 and st["status"] == "paused"
        ev = await _drain(q)
        assert [e["type"] for e in ev] == ["bar", "quote", "state"]
        assert ev[0]["ts"] == TODAY[0].ts.isoformat().replace("+00:00", "Z")
        await s.step(len(TODAY))
        assert s.status == "ended" and s.cursor == len(TODAY)

    asyncio.run(run())


def test_five_minute_view_bars() -> None:
    async def run() -> None:
        s = ReplaySession(
            user_id=1,
            instrument_id=22,
            day=DAYS[2],
            timeframe=Timeframe.M5,
            candles_1m=TODAY,
            speed=600,
            calendar=CAL,
        )
        q = s.subscribe()
        await _drain(q)
        await s.step(11)  # the 11th 1m bar closes the second 5m bucket
        bars = [e for e in await _drain(q) if e["type"] == "bar"]
        assert len(bars) == 2 and bars[0]["timeframe"] == "5m" and bars[0]["volume"] == 500

    asyncio.run(run())


def test_overlay_trades_and_determinism() -> None:
    async def run() -> tuple[list[dict], dict]:  # type: ignore[type-arg]
        s = _session(seed=11)
        assert s.warmup_bars == len(WARM)
        q = s.subscribe()
        await _drain(q)
        await s.step(len(TODAY))
        ev = await _drain(q)
        kinds = [e["type"] for e in ev]
        assert "signal" in kinds and "order" in kinds and "fill" in kinds and "trade" in kinds
        # an order is never filled on the bar that created it
        first_order = next(i for i, e in enumerate(ev) if e["type"] == "order")
        first_fill = next(i for i, e in enumerate(ev) if e["type"] == "fill")
        assert first_fill > first_order
        assert s.overlay is not None and len(s.overlay.trades) >= 1
        assert s.state()["overlay"]["engine"] in ("flat", "long")
        return _strip(s.overlay.fills), s.state()["overlay"]

    a = asyncio.run(run())
    b = asyncio.run(run())
    assert a == b  # same seed and data -> identical fills and final state


def test_rewind_rebuilds_identical_state() -> None:
    async def run() -> None:
        s = _session(seed=3)
        await s.step(40)
        snap40 = s.state()["overlay"]
        fills40 = _strip(s.overlay.fills)  # type: ignore[union-attr]
        await s.step(10)
        assert s.cursor == 50
        st = await s.step(-10)
        assert st["cursor"] == 40 and s.state()["overlay"] == snap40
        assert _strip(s.overlay.fills) == fills40  # type: ignore[union-attr]
        target = TODAY[20].ts
        st = await s.seek(target)
        assert st["cursor"] == 20
        st = await s.seek(TODAY[60].ts)
        assert st["cursor"] == 60

    asyncio.run(run())


def test_play_pause_speed_and_manager() -> None:
    async def run() -> None:
        m = ReplayManager()
        s = m.add(_session(strategy=False))
        assert m.get(s.session_id, 1) is s and m.get(s.session_id, 2) is None
        s.set_speed(600)
        s.play()
        await asyncio.sleep(0.45)
        st = await s.pause()
        assert st["status"] == "paused" and 2 <= st["cursor"] <= 8
        for _ in range(4):
            m.add(_session(strategy=False))
        try:
            m.add(_session(strategy=False))
            raise AssertionError("cap not enforced")
        except RuntimeError:
            pass
        assert await m.remove(s.session_id, 1) and m.get(s.session_id, 1) is None
        s2 = m.list_for(1)[0]
        s2.last_activity = datetime(2020, 1, 1, tzinfo=UTC)
        assert await m.sweep() == 1

    asyncio.run(run())


def test_owner_rule_sees_stored_pcr_in_replay() -> None:
    """Mark 1, Stage 2: with PCR history the replay overlay blocks a PUT buy at PCR >= 2."""
    from core.models import OptionType
    from risk.market_history import PcrHistory, PcrPoint

    put = InstrumentMeta(
        instrument_id=22,
        symbol="NIFTY25NOV25000PE",
        segment=Segment.OPTIONS,
        lot_size=1,
        underlying_symbol="NIFTY",
        option_type=OptionType.PE,
    )
    pts = [
        PcrPoint(TODAY[0].ts - timedelta(minutes=1) + timedelta(minutes=3 * i), Decimal("2.5"), "x")
        for i in range(len(TODAY) // 3 + 2)
    ]

    async def run(history: PcrHistory | None) -> list[dict]:  # type: ignore[type-arg]
        s = ReplaySession(
            user_id=1,
            instrument_id=22,
            day=DAYS[2],
            timeframe=Timeframe.M1,
            candles_1m=TODAY,
            warmup_1m=WARM,
            strategy=_strategy(),
            strategy_version_id=1,
            meta=put,
            speed=600,
            seed=3,
            calendar=CAL,
            market_history=history,
        )
        q = s.subscribe()
        await s.step(len(TODAY))
        return await _drain(q)

    blocked = asyncio.run(run(PcrHistory(pts)))
    reasons = [r for e in blocked if e["type"] == "signal_rejected" for r in e["reasons"]]
    assert any("PCR" in r for r in reasons)
    assert not any(e["type"] == "fill" for e in blocked)

    free = asyncio.run(run(None))  # no history: the rule is skipped, as before Stage 2
    assert any(e["type"] == "fill" for e in free)
