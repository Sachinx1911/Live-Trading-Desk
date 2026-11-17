from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from core.calendar import nse_calendar
from core.models import Candle, Timeframe
from core.time import IST
from market_data.candles import session_minutes
from market_data.manager import ProviderManager, ProviderMode, SwitchEvent
from market_data.quality import find_duplicates, find_gaps
from providers.base import ConnectionState, ProviderHealth, ProviderInfo
from providers.fake import FakeMarketDataProvider

cal = nse_calendar()
DAY = date(2026, 11, 17)


def _c(ts: datetime, iid: int = 1) -> Candle:
    return Candle(
        instrument_id=iid, timeframe=Timeframe.M1, ts=ts, open=Decimal(1), high=Decimal(1),
        low=Decimal(1), close=Decimal(1), provider_id="fake", received_at=ts, is_demo=True,
    )  # fmt: skip


def test_find_gaps_and_duplicates() -> None:
    minutes = session_minutes(cal, DAY)
    present = [m for i, m in enumerate(minutes) if i not in (0, 1, 2, 100, 374)]
    gaps = find_gaps([_c(m) for m in present], cal, DAY)
    assert [(g.minutes, g.start) for g in gaps] == [
        (3, minutes[0]),
        (1, minutes[100]),
        (1, minutes[374]),
    ]
    assert gaps[0].end == minutes[2]
    assert find_gaps([_c(m) for m in minutes], cal, DAY) == []
    assert find_gaps([], cal, date(2026, 11, 15)) == []
    dups = find_duplicates([_c(minutes[5]), _c(minutes[5]), _c(minutes[6])])
    assert dups == [minutes[5]]


class _Clock:
    def __init__(self, at: datetime) -> None:
        self.at = at

    def __call__(self) -> datetime:
        return self.at


class _Fake2(FakeMarketDataProvider):
    @property
    def info(self) -> ProviderInfo:
        base = super().info
        return ProviderInfo(
            code="fake2",
            display_name="Fake 2",
            capabilities=base.capabilities,
            is_demo=True,
            supported_timeframes=base.supported_timeframes,
        )


async def _manager(mode: ProviderMode, clock: _Clock) -> tuple[ProviderManager, list[SwitchEvent]]:
    a = FakeMarketDataProvider(seed=1, tick_interval=0, today=DAY)
    b = _Fake2(seed=2, tick_interval=0, today=DAY)
    events: list[SwitchEvent] = []

    async def on_switch(ev: SwitchEvent) -> None:
        events.append(ev)

    m = ProviderManager(
        a, b, mode=mode, calendar=cal, failover_after_s=15, on_switch=on_switch, clock=clock
    )
    return m, events


async def test_failover_promotes_secondary_after_grace_and_never_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _Clock(datetime(2026, 11, 17, 10, 0, tzinfo=IST).astimezone(UTC))
    m, events = await _manager(ProviderMode.FAILOVER, clock)
    primary, secondary = m.providers["fake"], m.providers["fake2"]
    await secondary.connect()
    state = {"primary": ConnectionState.DISCONNECTED}

    async def ph() -> ProviderHealth:
        return ProviderHealth(code="fake", state=state["primary"])

    monkeypatch.setattr(primary, "health", ph)
    assert await m.check() is None  # starts the unhealthy clock
    clock.at += timedelta(seconds=10)
    assert await m.check() is None  # grace not elapsed
    clock.at += timedelta(seconds=6)
    ev = await m.check()
    assert ev is not None and ev.to_code == "fake2" and ev.automatic
    assert m.active_code == "fake2" and events == [ev]
    state["primary"] = ConnectionState.CONNECTED
    clock.at += timedelta(minutes=5)
    assert await m.check() is None and m.active_code == "fake2"  # never auto-switch back
    back = await m.switch_to("fake", reason="operator")
    assert back is not None and not back.automatic and m.active_code == "fake"


async def test_no_failover_when_market_closed_or_single_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed = _Clock(datetime(2026, 11, 17, 18, 0, tzinfo=IST).astimezone(UTC))
    m, _ = await _manager(ProviderMode.FAILOVER, closed)
    await m.providers["fake2"].connect()
    for _i in range(5):
        assert await m.check() is None
        closed.at += timedelta(seconds=20)
    assert m.active_code == "fake"
    single = ProviderManager(FakeMarketDataProvider(seed=3, tick_interval=0, today=DAY))
    assert single.mode == ProviderMode.SINGLE and await single.check() is None
    with pytest.raises(ValueError):
        ProviderManager(
            FakeMarketDataProvider(seed=3, tick_interval=0, today=DAY), mode=ProviderMode.FAILOVER
        )
    with pytest.raises(ValueError):
        await single.switch_to("nope", reason="x")
