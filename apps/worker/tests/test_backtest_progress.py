"""ProgressReporter: Redis progress key, step throttling and cancellation (fakeredis)."""

import orjson
import pytest
from fakeredis import FakeAsyncRedis

from worker.jobs.backtests import (
    JobCancelled,
    ProgressReporter,
    _downsample,
    cancel_key,
    progress_key,
)


@pytest.fixture
def redis() -> FakeAsyncRedis:
    return FakeAsyncRedis(decode_responses=True)


async def test_progress_is_throttled_and_written(redis: FakeAsyncRedis) -> None:
    rep = ProgressReporter(redis, "backtest", 7, step_pct=5)
    await rep.report(1, "start")
    await rep.report(3, "ignored")  # < 5 pct step since last write
    raw = await redis.get(progress_key("backtest", 7))
    assert raw is not None and orjson.loads(raw)["pct"] == 1.0
    await rep.report(10, "ten")
    assert orjson.loads(await redis.get(progress_key("backtest", 7)))["pct"] == 10.0
    await rep.report(100, "done")  # 100 always lands
    assert orjson.loads(await redis.get(progress_key("backtest", 7)))["message"] == "done"
    assert await redis.ttl(progress_key("backtest", 7)) > 0


async def test_cancel_flag_raises(redis: FakeAsyncRedis) -> None:
    rep = ProgressReporter(redis, "optimization", 3)
    await redis.set(cancel_key("optimization", 3), "1")
    with pytest.raises(JobCancelled):
        await rep.report(50, "half")
    assert rep.cancelled


def test_downsample_keeps_endpoints() -> None:
    pts = list(range(10_000))
    out = _downsample(pts, 2000)
    assert len(out) <= 2001 and out[0] == 0 and out[-1] == 9_999
    assert _downsample([1, 2, 3], 2000) == [1, 2, 3]
