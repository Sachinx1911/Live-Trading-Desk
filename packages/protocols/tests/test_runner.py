"""Runner: order, on_error, final status, cancel, results stored as JSON."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict

from core.notify.telegram import NullNotifier
from core.settings import Settings
from protocols.context import ActionContext
from protocols.registry import ActionError, ActionRegistry, StepSpec
from protocols.runner import execute_steps, plan

CALLS: list[str] = []


class Tag(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tag: str = ""


def _reg() -> ActionRegistry:
    reg = ActionRegistry()

    @reg.register("ok", "succeeds", "green", Tag)
    async def ok(ctx: ActionContext, a: Tag) -> dict[str, Any]:
        CALLS.append(f"ok:{a.tag}")
        return {"summary": f"ok {a.tag}", "value": Decimal("1.50"), "at": ctx.now()}

    @reg.register("boom", "fails", "green", Tag)
    async def boom(ctx: ActionContext, a: Tag) -> dict[str, Any]:
        CALLS.append(f"boom:{a.tag}")
        raise ActionError("nothing to do")

    return reg


def _ctx() -> ActionContext:
    return ActionContext(
        db=None,
        redis=None,
        settings=Settings(_env_file=None),  # type: ignore[call-arg]
        notifier=NullNotifier(),
        user_id=1,
        clock=lambda: datetime(2026, 11, 23, 4, 0, tzinfo=UTC),
    )


def _plan(*steps: tuple[str, str, str]) -> list[dict[str, Any]]:
    return plan([StepSpec(tool=t, args={"tag": g}, on_error=e) for t, g, e in steps])  # type: ignore[arg-type]


async def test_steps_run_in_order_and_succeed() -> None:
    CALLS.clear()
    out = await execute_steps(
        _plan(("ok", "a", "stop"), ("ok", "b", "stop"), ("ok", "c", "stop")), _reg(), _ctx()
    )
    assert CALLS == ["ok:a", "ok:b", "ok:c"]
    assert out.status == "succeeded"
    assert [s["status"] for s in out.steps] == ["succeeded"] * 3
    r = out.steps[0]
    assert r["result"]["value"] == "1.50" and r["result"]["at"].startswith("2026-11-23")
    assert r["started_at"] and r["finished_at"] and r["tool"] == "ok"
    assert out.summary == "ok: ok a | ok: ok b | ok: ok c"


async def test_on_error_stop_skips_the_rest() -> None:
    CALLS.clear()
    out = await execute_steps(
        _plan(("ok", "a", "stop"), ("boom", "b", "stop"), ("ok", "c", "stop")), _reg(), _ctx()
    )
    assert CALLS == ["ok:a", "boom:b"]
    assert [s["status"] for s in out.steps] == ["succeeded", "failed", "skipped"]
    assert out.steps[1]["error"] == "nothing to do"
    assert out.status == "partial"


async def test_on_error_continue_goes_on() -> None:
    CALLS.clear()
    out = await execute_steps(_plan(("boom", "a", "continue"), ("ok", "b", "stop")), _reg(), _ctx())
    assert CALLS == ["boom:a", "ok:b"]
    assert out.status == "partial"


async def test_all_failed_is_failed() -> None:
    out = await execute_steps(
        _plan(("boom", "a", "continue"), ("boom", "b", "stop")), _reg(), _ctx()
    )
    assert out.status == "failed"


async def test_unknown_tool_and_bad_args_fail_the_step_not_the_runner() -> None:
    planned = plan([StepSpec(tool="ghost"), StepSpec(tool="ok", args={"tag": 5})])
    planned[0]["on_error"] = "continue"
    planned[1]["on_error"] = "continue"
    out = await execute_steps(planned, _reg(), _ctx())
    assert out.steps[0]["error"] == "unknown action 'ghost'"
    assert out.steps[1]["error"].startswith("invalid args: tag:")
    assert out.status == "failed"


async def test_cancel_between_steps() -> None:
    CALLS.clear()
    seen: list[int] = []

    async def cancelled() -> bool:
        seen.append(1)
        return len(seen) > 1  # cancel after the first step

    progress: list[list[str]] = []

    async def on_progress(results: list[dict[str, Any]]) -> None:
        progress.append([r["status"] for r in results])

    out = await execute_steps(
        _plan(("ok", "a", "stop"), ("ok", "b", "stop")),
        _reg(),
        _ctx(),
        is_cancelled=cancelled,
        on_progress=on_progress,
    )
    assert CALLS == ["ok:a"]
    assert out.status == "cancelled"
    assert [s["status"] for s in out.steps] == ["succeeded", "skipped"]
    assert progress[0] == ["running", "pending"]
    assert progress[-1] == ["succeeded", "skipped"]
