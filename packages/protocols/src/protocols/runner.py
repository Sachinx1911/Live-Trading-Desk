"""Run the steps of a protocol in order. Pure orchestration: no DB rows are written here;
the caller persists progress through `on_progress` (the worker commits after every step)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from core.logging import get_logger
from protocols.context import ActionContext
from protocols.jsonable import jsonable
from protocols.registry import ActionError, ActionRegistry, StepSpec

log = get_logger(__name__)

StepStatus = str  # pending | running | succeeded | failed | skipped
ProgressFn = Callable[[list[dict[str, Any]]], Awaitable[None]]
CancelledFn = Callable[[], Awaitable[bool]]


@dataclass(frozen=True)
class RunOutcome:
    status: str  # succeeded | partial | failed | cancelled
    steps: list[dict[str, Any]]
    summary: str


def plan(steps: list[StepSpec]) -> list[dict[str, Any]]:
    """The step list as stored on a run before it executes (what the owner confirms)."""
    return [
        {"tool": s.tool, "args": dict(s.args), "on_error": s.on_error, "status": "pending"}
        for s in steps
    ]


def _short_error(exc: BaseException) -> str:
    if isinstance(exc, ValidationError):
        return "invalid args: " + "; ".join(
            f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
        )
    if isinstance(exc, ActionError):
        return str(exc)
    return f"{type(exc).__name__}: {exc}"[:500]


def final_status(results: list[dict[str, Any]]) -> str:
    ok = sum(1 for r in results if r["status"] == "succeeded")
    if ok == len(results):
        return "succeeded"
    return "failed" if ok == 0 else "partial"


def summarise(results: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for r in results:
        if r["status"] == "succeeded":
            res = r.get("result") or {}
            parts.append(f"{r['tool']}: {res.get('summary', 'ok')}")
        elif r["status"] == "failed":
            parts.append(f"{r['tool']}: FAILED ({r.get('error')})")
        elif r["status"] == "skipped":
            parts.append(f"{r['tool']}: skipped")
    return " | ".join(parts)[:2000]


async def execute_steps(
    planned: list[dict[str, Any]],
    registry: ActionRegistry,
    ctx: ActionContext,
    *,
    is_cancelled: CancelledFn | None = None,
    on_progress: ProgressFn | None = None,
) -> RunOutcome:
    """Execute `planned` (see `plan`) in order. A failing step with on_error=stop marks the
    remaining steps skipped; with on_error=continue the run goes on. A cancel request is
    honoured between steps (a step already running is not interrupted)."""
    results = [dict(p) for p in planned]
    stopped = False
    for i, step in enumerate(results):
        if stopped:
            step["status"] = "skipped"
            continue
        if is_cancelled is not None and await is_cancelled():
            for rest in results[i:]:
                rest["status"] = "skipped"
            if on_progress:
                await on_progress(results)
            return RunOutcome("cancelled", results, "cancelled before " + step["tool"])
        started = ctx.now()
        step["status"] = "running"
        step["started_at"] = started.isoformat()
        if on_progress:
            await on_progress(results)
        spec = registry.get(step["tool"])
        try:
            if spec is None:
                raise ActionError(f"unknown action {step['tool']!r}")
            args = spec.parse_args(step.get("args") or {})
            async with ctx.savepoint():
                out = await spec.fn(ctx, args)
            step["status"] = "succeeded"
            step["result"] = jsonable(out)
        except Exception as exc:
            step["status"] = "failed"
            step["error"] = _short_error(exc)
            log.warning("protocol.step_failed", tool=step["tool"], error=step["error"])
            if step.get("on_error", "stop") == "stop":
                stopped = True
        step["finished_at"] = ctx.now().isoformat()
        if on_progress:
            await on_progress(results)
    if on_progress and stopped:
        await on_progress(results)
    return RunOutcome(final_status(results), results, summarise(results))
