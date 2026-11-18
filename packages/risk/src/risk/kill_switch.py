"""Kill switch flags in Redis (checked on every order) plus the event dict the caller
persists to `kill_switch_events`. Three scopes: global, account:{id}, strategy:{id}."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import orjson
from redis.asyncio import Redis

from core.time import utcnow

SCOPES = ("global", "account", "strategy")


def _key(scope: str) -> str:
    return f"kill:{scope}"


def _validate(scope: str) -> None:
    kind = scope.split(":", 1)[0]
    if kind not in SCOPES or (kind != "global" and ":" not in scope):
        raise ValueError(
            f"bad kill switch scope {scope!r}; use global | account:<id> | strategy:<id>"
        )


class KillSwitch:
    def __init__(self, redis: Redis) -> None:
        self._r = redis

    async def is_active(self, scope: str) -> bool:
        _validate(scope)
        n: int = await self._r.exists(_key(scope))
        return n == 1

    async def any_active(
        self, account_id: int | None, strategy_version_id: int | None
    ) -> list[str]:
        scopes = ["global"]
        if account_id is not None:
            scopes.append(f"account:{account_id}")
        if strategy_version_id is not None:
            scopes.append(f"strategy:{strategy_version_id}")
        vals = await self._r.mget([_key(s) for s in scopes])
        return [s for s, v in zip(scopes, vals, strict=True) if v is not None]

    async def activate(
        self, scope: str, reason: str, by: str, *, now: datetime | None = None
    ) -> dict[str, Any]:
        _validate(scope)
        ts = (now or utcnow()).isoformat()
        payload = {"reason": reason, "by": by, "ts": ts}
        await self._r.set(_key(scope), orjson.dumps(payload))  # no TTL: only a human clears it
        return self._event(scope, "activate", reason, by, ts)

    async def deactivate(
        self, scope: str, reason: str, by: str, *, now: datetime | None = None
    ) -> dict[str, Any]:
        _validate(scope)
        ts = (now or utcnow()).isoformat()
        await self._r.delete(_key(scope))
        return self._event(scope, "deactivate", reason, by, ts)

    async def status(self, scope: str) -> dict[str, Any] | None:
        _validate(scope)
        raw = await self._r.get(_key(scope))
        return None if raw is None else dict(orjson.loads(raw))

    @staticmethod
    def _event(scope: str, action: str, reason: str, by: str, ts: str) -> dict[str, Any]:
        kind, _, sid = scope.partition(":")
        return {
            "scope": kind,
            "scope_id": int(sid) if sid else None,
            "action": action,
            "reason": reason,
            "triggered_by": by,
            "ts": ts,
        }
