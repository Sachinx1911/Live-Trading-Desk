"""Minimal in-process async event bus. Redis pub/sub bridging is added in market_data."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

Handler = Callable[[Any], Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)

    def subscribe(self, topic: str, handler: Handler) -> Callable[[], None]:
        self._handlers[topic].append(handler)

        def unsubscribe() -> None:
            self._handlers[topic].remove(handler)

        return unsubscribe

    async def publish(self, topic: str, event: Any) -> None:
        handlers = list(self._handlers.get(topic, ()))
        if handlers:
            await asyncio.gather(*(h(event) for h in handlers))
