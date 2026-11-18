from __future__ import annotations

import pytest
from fakeredis import aioredis as fakeredis

from ai.llm import BudgetExceededError, DailyTokenBudget, TokenBudget, Usage
from ai.llm.budget import day_key


def test_job_budget_checks_reserve_then_consumes() -> None:
    b = TokenBudget(limit=1000)
    b.check(reserve=900)
    b.consume(Usage(500, 300))
    assert b.used == 800 and b.remaining == 200 and b.calls == 1 and not b.exhausted
    with pytest.raises(BudgetExceededError) as exc:
        b.check(reserve=201)
    assert exc.value.scope == "job" and exc.value.used == 800 and exc.value.limit == 1000
    b.check(reserve=200)  # exactly at the limit is allowed
    b.consume(Usage(150, 100))
    assert b.exhausted and b.remaining == 0


def test_job_budget_rejects_non_positive_limit() -> None:
    with pytest.raises(ValueError, match="positive"):
        TokenBudget(limit=0)


async def test_daily_budget_is_shared_through_redis() -> None:
    redis = fakeredis.FakeRedis(decode_responses=True)
    a = DailyTokenBudget(redis, limit=1000)
    b = DailyTokenBudget(redis, limit=1000)  # another process, same counter
    assert await a.used() == 0
    await a.check(reserve=1000)
    assert await a.consume(Usage(600, 100)) == 700
    assert await b.used() == 700
    with pytest.raises(BudgetExceededError) as exc:
        await b.check(reserve=301)
    assert exc.value.scope == "daily"
    assert await redis.ttl(day_key()) > 0  # the counter expires on its own


async def test_daily_budget_rejects_non_positive_limit() -> None:
    with pytest.raises(ValueError, match="positive"):
        DailyTokenBudget(fakeredis.FakeRedis(), limit=0)
