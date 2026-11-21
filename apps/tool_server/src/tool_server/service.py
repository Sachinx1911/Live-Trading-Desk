"""The one path every tool call takes, whichever transport it arrived on (HTTP or MCP).

    authenticate (sha256 lookup, revoked refused, last_used_at updated)
    -> tool known? -> enabled in this stage and at or below the effective level?
    -> rate limit -> validate args -> run with the tool's timeout
    -> write one `tool_calls` row (ok | error | refused) -> answer

Nothing here can place, modify or cancel an order: the catalogue holds no such tool, and
red tools are refused even if someone registered one. The presented token, broker
credentials and SECRETS_KEY are never returned or logged: arguments and error texts are
scrubbed before they are stored, and unexpected exceptions are reported by type only.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

import orjson
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.db.models import ToolCall
from core.db.models._enums import ActorType
from core.logging import get_logger
from core.notify import Notifier
from core.notify.telegram import NullNotifier
from core.secrets import SecretBox
from core.services.tool_tokens import lookup_token, touch
from core.settings import Settings
from core.time import utcnow
from protocols.catalogue import CATALOGUE, STAGE, ToolCatalogue, ToolSpec, effective_level, run_tool
from protocols.context import ActionContext
from protocols.registry import ActionError
from tool_server import views_tool as views_tool  # registers the record_view tool
from tool_server.ratelimit import RateLimiter

log = get_logger(__name__)

Status = Literal["ok", "error", "refused"]
Transport = Literal["http", "mcp"]
LIST_TOOL = "tools/list"
CONNECT_TOOL = "mcp/connect"
REDACTED = "[redacted]"
SENSITIVE_KEY = re.compile(
    r"(token|secret|password|passwd|api[_-]?key|authorization|credential|cookie|session)", re.I
)
TOKEN_LIKE = re.compile(r"ltd_[A-Za-z0-9_\-]{16,}")
MAX_ARGS_JSON = 4000
MAX_STR = 200
MAX_ERROR = 500


def bearer(header: str | None) -> str | None:
    if not header:
        return None
    scheme, _, value = header.strip().partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        return None
    return value.strip()


@dataclass(frozen=True)
class Caller:
    status: Literal["ok", "missing", "invalid", "revoked"]
    token_id: int | None = None
    user_id: int | None = None
    name: str | None = None
    max_level: str = "green"


@dataclass
class Outcome:
    status: Status
    http_status: int
    code: str
    result: dict[str, Any] | None = None
    message: str | None = None
    call_id: int | None = None
    tool: str | None = None  # the tool name as logged (scrubbed); echoed instead of the input

    def body(self, tool: str) -> dict[str, Any]:
        name = self.tool if self.tool is not None else tool
        out: dict[str, Any] = {"ok": self.status == "ok", "tool": name, "call_id": self.call_id}
        if self.status == "ok":
            out["result"] = self.result
        else:
            out["error"] = {"code": self.code, "message": self.message}
        return out


@dataclass
class ToolService:
    settings: Settings
    session_factory: async_sessionmaker[AsyncSession]
    redis: Any
    catalogue: ToolCatalogue = CATALOGUE
    secret_box: SecretBox | None = None
    notifier: Notifier = field(default_factory=NullNotifier)
    clock: Callable[[], datetime] = utcnow
    limiter: RateLimiter | None = None

    def __post_init__(self) -> None:
        if self.limiter is None:
            self.limiter = RateLimiter(self.settings.tool_server_rate_per_minute)
        # Values that must never be stored or echoed, even if a caller sends them.
        self._never: list[str] = [
            v
            for v in (
                self.settings.secrets_key.get_secret_value(),
                self.settings.jwt_secret.get_secret_value(),
            )
            if v and len(v) >= 8
        ]

    # ------------------------------------------------------------------ scrubbing
    def _scrub_text(self, text: str, presented: str | None) -> str:
        for v in (*self._never, presented or ""):
            if v and len(v) >= 8:
                text = text.replace(v, REDACTED)
        return TOKEN_LIKE.sub(REDACTED, text)

    def scrub(self, value: Any, presented: str | None, depth: int = 0) -> Any:
        if depth > 6:
            return "[nested]"
        if isinstance(value, dict):
            return {
                str(k)[:64]: REDACTED
                if SENSITIVE_KEY.search(str(k))
                else self.scrub(v, presented, depth + 1)
                for k, v in list(value.items())[:50]
            }
        if isinstance(value, list | tuple):
            return [self.scrub(v, presented, depth + 1) for v in list(value)[:50]]
        if isinstance(value, str):
            s = self._scrub_text(value, presented)
            return s if len(s) <= MAX_STR else s[:MAX_STR] + "..."
        if isinstance(value, int) and not isinstance(value, bool) and abs(value) > 2**53:
            return str(value)  # outside JSON's safe range; kept readable, never fails the log
        if value is None or isinstance(value, bool | int | float):
            return value
        return f"<{type(value).__name__}>"

    def safe_args(self, args: Any, presented: str | None) -> dict[str, Any]:
        if not isinstance(args, dict):
            return {"_invalid": f"<{type(args).__name__}>"}
        clean = self.scrub(args, presented)
        if len(orjson.dumps(clean)) > MAX_ARGS_JSON:
            return {"_truncated": True, "keys": list(clean)[:20]}
        return clean  # type: ignore[no-any-return]

    # ------------------------------------------------------------------ auth + levels
    async def authenticate(self, presented: str | None) -> Caller:
        async with self.session_factory() as db:
            found = await lookup_token(db, presented)
            if found.status != "ok" or found.token is None:
                tok = found.token
                return Caller(found.status, tok.id if tok else None, tok.user_id if tok else None)
            t = found.token
            await touch(db, t.id, self.clock())
            await db.commit()
            return Caller("ok", t.id, t.user_id, t.name, t.max_level)

    def limit_for(self, caller: Caller) -> str:
        return effective_level(self.settings.tool_server_max_level, caller.max_level)

    def visible(self, caller: Caller) -> list[ToolSpec]:
        if caller.status != "ok":
            return []
        return self.catalogue.callable_at(self.limit_for(caller))

    def catalogue_view(self, caller: Caller) -> dict[str, Any]:
        limit = self.limit_for(caller)
        tools = self.catalogue.callable_at(limit)
        names = {t.name for t in tools}
        planned = [
            {
                "name": t.name,
                "level": t.level,
                "tier": t.tier,
                "planned_stage": t.planned_stage,
                "reason": "planned for a later stage"
                if not t.enabled
                else f"above the effective level ({limit})",
            }
            for t in self.catalogue.all()
            if t.name not in names
        ]
        return {
            "domain": "trading",
            "stage": STAGE,
            "effective_level": limit,
            "caller": {"name": caller.name, "max_level": caller.max_level},
            "tools": [t.describe() for t in tools],
            "not_callable": planned,
        }

    def _refusal_for(self, spec: ToolSpec, limit: str) -> str | None:
        if spec.level == "red":
            return f"{spec.name} is red; red actions are never served by the tool server"
        if not spec.enabled:
            return (
                f"{spec.name} is {spec.level} ({spec.tier}) and planned for Stage "
                f"{spec.planned_stage}; this server is at Stage {STAGE}"
            )
        if not spec.callable_at(limit):
            return (
                f"{spec.name} is {spec.level} ({spec.tier}); the effective level for this "
                f"token is {limit}"
            )
        return None

    # ------------------------------------------------------------------ logging
    async def _log(
        self,
        *,
        caller: Caller,
        transport: Transport,
        tool: str,
        level: str | None,
        args: dict[str, Any],
        outcome: Outcome,
        started: float,
        presented: str | None,
    ) -> Outcome:
        meta: dict[str, Any] = {"code": outcome.code}
        if outcome.result is not None:
            r = outcome.result
            meta.update(
                source=r.get("source"),
                freshness=r.get("freshness"),
                is_demo=r.get("is_demo"),
                rows={k: len(v) for k, v in r.items() if isinstance(v, list)},
            )
        if outcome.message:
            outcome.message = self._scrub_text(outcome.message, presented)[:MAX_ERROR]
        row = ToolCall(
            ts=self.clock(),
            token_id=caller.token_id,
            transport=transport,
            tool=self._scrub_text(tool, presented)[:64] or "?",
            level=level,
            args=args,
            status=outcome.status,
            error=outcome.message if outcome.status != "ok" else None,
            duration_ms=int((time.monotonic() - started) * 1000),
            result_meta=meta,
        )
        try:
            async with self.session_factory() as db:
                db.add(row)
                await db.commit()
                outcome.call_id = row.id
                outcome.tool = row.tool
        except Exception as exc:
            # The authority log is part of the contract: no log row, no answer.
            log.error("tool_server.log_failed", tool=row.tool, error=type(exc).__name__)
            return Outcome("error", 503, "log_unavailable", None, "the call could not be logged")
        log.info(
            "tool_server.call",
            tool=row.tool,
            transport=transport,
            status=outcome.status,
            code=outcome.code,
            token_id=caller.token_id,
            duration_ms=row.duration_ms,
        )
        return outcome

    async def log_refusal(
        self, *, presented: str | None, caller: Caller, transport: Transport, tool: str
    ) -> Outcome:
        out = Outcome("refused", 401, "unauthorized", None, f"{caller.status} token")
        return await self._log(
            caller=caller,
            transport=transport,
            tool=tool,
            level=None,
            args={},
            outcome=out,
            started=time.monotonic(),
            presented=presented,
        )

    # ------------------------------------------------------------------ the call
    async def call(
        self, presented: str | None, transport: Transport, name: str, args: Any
    ) -> Outcome:
        started = time.monotonic()
        caller = await self.authenticate(presented)
        spec = self.catalogue.get(name)
        level = spec.level if spec is not None else None
        logged_args = self.safe_args(args, presented)

        async def done(o: Outcome) -> Outcome:
            return await self._log(
                caller=caller,
                transport=transport,
                tool=name,
                level=level,
                args=logged_args,
                outcome=o,
                started=started,
                presented=presented,
            )

        if caller.status != "ok":
            return await done(
                Outcome("refused", 401, "unauthorized", None, f"{caller.status} token")
            )
        if spec is None:
            return await done(
                Outcome("refused", 404, "unknown_tool", None, f"no tool named {name!r}")
            )
        refusal = self._refusal_for(spec, self.limit_for(caller))
        if refusal is not None:
            return await done(Outcome("refused", 403, "level_not_allowed", None, refusal))
        assert self.limiter is not None
        if caller.token_id is None or not self.limiter.allow(caller.token_id):
            return await done(Outcome("refused", 429, "rate_limited", None, "rate limit exceeded"))
        if not isinstance(args, dict):
            return await done(
                Outcome("error", 422, "bad_args", None, "arguments must be a JSON object")
            )
        return await done(await self._run(spec, caller, args))

    async def _run(self, spec: ToolSpec, caller: Caller, args: dict[str, Any]) -> Outcome:
        async with self.session_factory() as db:
            ctx = ActionContext(
                db=db,
                redis=self.redis,
                settings=self.settings,
                notifier=self.notifier,
                user_id=caller.user_id,
                actor=ActorType.AI,
                secret_box=self.secret_box,
                clock=self.clock,
            )
            try:
                result = await asyncio.wait_for(run_tool(spec, ctx, args), timeout=spec.timeout_s)
                if spec.writes:
                    await db.commit()
                else:
                    await _rollback(db)
                return Outcome("ok", 200, "ok", result)
            except ValidationError as exc:
                await _rollback(db)
                errs = [
                    f"{'.'.join(str(p) for p in e['loc']) or 'args'}: {e['msg']}"
                    for e in exc.errors()
                ]
                return Outcome("error", 422, "bad_args", None, "; ".join(errs))
            except ActionError as exc:
                await _rollback(db)
                return Outcome("error", 422, "tool_error", None, str(exc))
            except TimeoutError:
                await _rollback(db)
                return Outcome(
                    "error",
                    504,
                    "timeout",
                    None,
                    f"{spec.name} took longer than {spec.timeout_s} s",
                )
            except Exception as exc:
                await _rollback(db)
                log.warning("tool_server.tool_failed", tool=spec.name, error=type(exc).__name__)
                return Outcome(
                    "error", 500, "internal", None, f"internal error ({type(exc).__name__})"
                )


async def _rollback(db: AsyncSession) -> None:
    """Read-only tools leave nothing behind; a cancelled (timed-out) call may have left the
    connection unusable, in which case closing the session discards it."""
    try:
        await db.rollback()
    except Exception as exc:  # pragma: no cover - depends on where the cancel landed
        log.warning("tool_server.rollback_failed", error=type(exc).__name__)
