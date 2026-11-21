"""Per-token rate limit: a simple in-memory token bucket (one process, loopback service)."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class _Bucket:
    tokens: float
    updated: float


class RateLimiter:
    def __init__(self, per_minute: int, clock: Callable[[], float] = time.monotonic) -> None:
        if per_minute < 1:
            raise ValueError("per_minute must be at least 1")
        self.capacity = float(per_minute)
        self.refill_per_s = per_minute / 60.0
        self._clock = clock
        self._buckets: dict[int, _Bucket] = {}

    def allow(self, key: int) -> bool:
        now = self._clock()
        b = self._buckets.get(key)
        if b is None:
            b = self._buckets[key] = _Bucket(self.capacity, now)
        b.tokens = min(self.capacity, b.tokens + (now - b.updated) * self.refill_per_s)
        b.updated = now
        if b.tokens < 1.0:
            return False
        b.tokens -= 1.0
        return True
