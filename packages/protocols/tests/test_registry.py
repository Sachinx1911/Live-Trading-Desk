"""Action registry and protocol validation (JSON only, validated against the registry)."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from protocols import REGISTRY
from protocols.builtin import BUILTINS
from protocols.context import ActionContext
from protocols.registry import (
    ActionRegistry,
    ProtocolSpec,
    StepSpec,
    max_risk,
    validate_steps,
)

REQUIRED = {
    "health_check": "green",
    "broker_sessions": "green",
    "regime_summary": "green",
    "pcr_now": "green",
    "paper_status": "green",
    "todays_events": "green",
    "recent_alerts": "green",
    "kill_switch_on": "yellow",
    "stop_paper_strategies": "yellow",
    "close_paper_positions": "yellow",
}


class NArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    n: int = 1


def _reg() -> ActionRegistry:
    reg = ActionRegistry()

    @reg.register("look", "read", "green", NArgs)
    async def look(ctx: ActionContext, a: NArgs) -> dict[str, Any]:
        return {"n": a.n}

    @reg.register("money", "red action", "red")
    async def money(ctx: ActionContext, a: Any) -> dict[str, Any]:
        return {}

    return reg


def test_default_registry_has_required_actions_with_risk_levels() -> None:
    cat = {a["name"]: a for a in REGISTRY.catalogue()}
    for name, risk in REQUIRED.items():
        assert cat[name]["risk"] == risk
        assert cat[name]["description"]
        assert cat[name]["args_schema"]["type"] == "object"


def test_no_action_names_an_order_path() -> None:
    for name in REGISTRY.names():
        assert "order" not in name and "live" not in name


def test_builtins_are_valid_and_match_the_plan() -> None:
    codes = {p.code: p for p in BUILTINS}
    assert set(codes) == {
        "market_open",
        "market_close",
        "shutdown",
        "clean_slate",
        "health_check",
        "review",
    }
    for p in BUILTINS:
        assert validate_steps(p.steps, p.confirm_required, REGISTRY) == []
    assert codes["shutdown"].confirm_required is True
    assert codes["clean_slate"].confirm_required is False  # kill switch on is immediate
    assert codes["clean_slate"].steps[0].tool == "kill_switch_on"
    assert [s.tool for s in codes["market_open"].steps] == [
        "health_check",
        "broker_sessions",
        "regime_summary",
        "pcr_now",
        "todays_events",
    ]


def test_unknown_action_and_bad_args_are_reported() -> None:
    reg = _reg()
    steps = [
        StepSpec(tool="nope"),
        StepSpec(tool="look", args={"n": "x"}),
        StepSpec(tool="look", args={"extra": 1}),
    ]
    errs = validate_steps(steps, False, reg)
    assert len(errs) == 3
    assert "unknown action 'nope'" in errs[0]
    assert errs[1].startswith("step 2 (look): n:")
    assert "extra" in errs[2]


def test_red_action_requires_confirm() -> None:
    reg = _reg()
    steps = [StepSpec(tool="look"), StepSpec(tool="money")]
    errs = validate_steps(steps, False, reg)
    assert errs == ["step 2 (money): red action; the protocol must set confirm_required"]
    assert validate_steps(steps, True, reg) == []
    assert max_risk(steps, reg) == "red"
    assert max_risk([StepSpec(tool="look")], reg) == "green"


def test_duplicate_and_bad_risk_registration_refused() -> None:
    reg = _reg()
    with pytest.raises(ValueError, match="duplicate"):
        reg.register("look", "again", "green")(lambda c, a: None)  # type: ignore[arg-type,return-value]
    with pytest.raises(ValueError, match="risk"):
        reg.register("x", "y", "purple")  # type: ignore[arg-type]


@pytest.mark.parametrize("code", ["A", "x", "has-dash", "runs", "actions", "9abc"])
def test_protocol_code_rules(code: str) -> None:
    with pytest.raises(ValidationError):
        ProtocolSpec(code=code, name="n", steps=[StepSpec(tool="health_check")])


def test_step_shape_is_json_only() -> None:
    with pytest.raises(ValidationError):
        StepSpec.model_validate({"tool": "health_check", "code": "import os"})
    with pytest.raises(ValidationError):
        StepSpec.model_validate({"tool": "health_check", "on_error": "retry"})
    with pytest.raises(ValidationError):
        ProtocolSpec(code="empty", name="n", steps=[])
