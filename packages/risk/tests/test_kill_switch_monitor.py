from decimal import Decimal

import pytest
from fakeredis import aioredis as fakeredis

from risk.kill_switch import KillSwitch
from risk.monitor_rules import MonitorAction, MonitorInput, evaluate


async def test_kill_switch_roundtrip() -> None:
    ks = KillSwitch(fakeredis.FakeRedis())
    assert not await ks.is_active("global")
    ev = await ks.activate("account:7", "daily loss", "monitor")
    assert ev["scope"] == "account" and ev["scope_id"] == 7 and ev["action"] == "activate"
    assert await ks.is_active("account:7")
    assert await ks.any_active(7, 3) == ["account:7"]
    await ks.activate("global", "manual", "owner")
    assert await ks.any_active(7, None) == ["global", "account:7"]
    st = await ks.status("global")
    assert st is not None and st["by"] == "owner"
    ev2 = await ks.deactivate("account:7", "reviewed", "owner")
    assert ev2["action"] == "deactivate"
    assert await ks.any_active(7, 3) == ["global"]


async def test_kill_switch_bad_scope() -> None:
    ks = KillSwitch(fakeredis.FakeRedis())
    with pytest.raises(ValueError):
        await ks.is_active("account")


@pytest.mark.parametrize(
    "inp, expected",
    [
        (MonitorInput(5.0, True, 1, False, Decimal(0), Decimal(2000)), MonitorAction.NONE),
        (MonitorInput(120.0, True, 1, False, Decimal(0), Decimal(2000)), MonitorAction.KILL_GLOBAL),
        (MonitorInput(120.0, True, 0, False, Decimal(0), Decimal(2000)), MonitorAction.NONE),
        (MonitorInput(120.0, False, 2, False, Decimal(0), Decimal(2000)), MonitorAction.NONE),
        (MonitorInput(None, True, 1, False, Decimal(0), Decimal(2000)), MonitorAction.KILL_GLOBAL),
        (MonitorInput(1.0, True, 0, True, Decimal(0), Decimal(2000)), MonitorAction.KILL_ACCOUNT),
        (MonitorInput(1.0, True, 0, False, Decimal(-1800), Decimal(2000)), MonitorAction.WARN),
        (
            MonitorInput(1.0, True, 0, False, Decimal(-2000), Decimal(2000)),
            MonitorAction.KILL_ACCOUNT,
        ),
        (MonitorInput(1.0, True, 0, False, Decimal(500), Decimal(2000)), MonitorAction.NONE),
    ],
)
def test_monitor_rules(inp: MonitorInput, expected: MonitorAction) -> None:
    assert evaluate(inp).action == expected
