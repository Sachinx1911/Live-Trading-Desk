"""Token budgets (ADR-009: per-job budgets are mandatory).

`TokenBudget` is the hard per-job stop: a job that would exceed it does not make the call.
`DailyTokenBudget` is the platform-wide ceiling (`AI_DAILY_TOKEN_BUDGET`) kept in Redis so
every process (API, worker) shares one counter per UTC day.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from redis.asyncio import Redis

from ai.llm.provider import LLMError, Usage
from core.time import utcnow

DAY_KEY_TTL_SECONDS = 2 * 24 * 3600


class BudgetExceededError(LLMError):
    def __init__(self, scope: str, used: int, limit: int, reserve: int = 0) -> None:
        super().__init__(
            f"{scope} token budget exceeded: used {used} + reserve {reserve} > limit {limit}"
        )
        self.scope = scope
        self.used = used
        self.limit = limit
        self.reserve = reserve


@dataclass
class TokenBudget:
    """Per-job budget. `check(reserve)` is called *before* a call with the worst-case
    tokens it may consume; `consume()` records what it actually used."""

    limit: int
    used: int = 0
    calls: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        if self.limit <= 0:
            raise ValueError("token budget limit must be positive")

    @property
    def remaining(self) -> int:
        return max(self.limit - self.used, 0)

    @property
    def exhausted(self) -> bool:
        return self.used >= self.limit

    def check(self, reserve: int = 0) -> None:
        if self.used + reserve > self.limit:
            raise BudgetExceededError("job", self.used, self.limit, reserve)

    def consume(self, usage: Usage) -> None:
        self.used += usage.total
        self.calls += 1


def day_key(prefix: str = "ai:tokens") -> str:
    return f"{prefix}:{utcnow().date().isoformat()}"


class DailyTokenBudget:
    """Shared per-day ceiling in Redis. Over-consumption by one in-flight call is accepted
    (the counter is incremented after the fact); the *next* call is refused."""

    def __init__(self, redis: Redis, limit: int, prefix: str = "ai:tokens") -> None:
        if limit <= 0:
            raise ValueError("daily token budget limit must be positive")
        self.redis = redis
        self.limit = limit
        self.prefix = prefix

    async def used(self) -> int:
        raw = await self.redis.get(day_key(self.prefix))
        return int(raw) if raw else 0

    async def check(self, reserve: int = 0) -> None:
        used = await self.used()
        if used + reserve > self.limit:
            raise BudgetExceededError("daily", used, self.limit, reserve)

    async def consume(self, usage: Usage) -> int:
        key = day_key(self.prefix)
        total = int(await self.redis.incrby(key, usage.total))
        await self.redis.expire(key, DAY_KEY_TTL_SECONDS)
        return total
