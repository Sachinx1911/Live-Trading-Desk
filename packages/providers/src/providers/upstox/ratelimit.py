"""Multi-window token-bucket limiter for the Upstox REST API.

Standard APIs allow 50 req/s, 500 req/min and 2000 req/30 min, enforced together.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Window:
    limit: int
    seconds: float


DEFAULT_WINDOWS: tuple[Window, ...] = (
    Window(50, 1.0),
    Window(500, 60.0),
    Window(2000, 1800.0),
)


class MultiWindowRateLimiter:
    """Sliding-window limiter: `acquire()` waits until a request fits in every window."""

    def __init__(
        self,
        windows: tuple[Window, ...] = DEFAULT_WINDOWS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._windows = windows
        self._clock = clock
        self._stamps: list[deque[float]] = [deque() for _ in windows]
        self._lock = asyncio.Lock()

    def _wait_needed(self, now: float) -> float:
        wait = 0.0
        for w, stamps in zip(self._windows, self._stamps, strict=True):
            while stamps and now - stamps[0] >= w.seconds:
                stamps.popleft()
            if len(stamps) >= w.limit:
                wait = max(wait, w.seconds - (now - stamps[0]))
        return wait

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = self._clock()
                wait = self._wait_needed(now)
                if wait <= 0:
                    for stamps in self._stamps:
                        stamps.append(now)
                    return
                await asyncio.sleep(wait)

    def would_wait(self) -> float:
        """Seconds a request would have to wait right now (0 = immediate)."""
        return self._wait_needed(self._clock())
