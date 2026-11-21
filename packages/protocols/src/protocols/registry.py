"""Action registry: the seed of the Stage 4 tool catalogue (docs/mark-1-plan.md §2.3).

A protocol is JSON only (CLAUDE.md rule 4): a list of steps naming a registered action and
its arguments. Nothing a user or an LLM writes is ever executed as code; the registry maps a
name to a function written here, and the arguments are validated by that action's Pydantic
model before the call.

Risk levels follow plan §2.3: green = read only, yellow = changes (paper changes carry the
owner's standing permission), red = money or safety. A protocol that contains a red action
must have `confirm_required = true`; this is checked when the protocol is saved and again
when a run starts.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

if TYPE_CHECKING:
    from protocols.context import ActionContext

RiskLevel = Literal["green", "yellow", "red"]
RISK_ORDER: dict[str, int] = {"green": 0, "yellow": 1, "red": 2}
OnError = Literal["stop", "continue"]

CODE_RE = re.compile(r"^[a-z][a-z0-9_]{1,47}$")
RESERVED_CODES = frozenset({"runs", "actions"})
MAX_STEPS = 30

ActionFn = Callable[["ActionContext", Any], Awaitable[dict[str, Any]]]


class NoArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ActionError(Exception):
    """Raised by an action when it could not do what it is for; the step is marked failed."""


@dataclass(frozen=True)
class ActionSpec:
    name: str
    description: str
    risk: RiskLevel
    args_model: type[BaseModel]
    fn: ActionFn

    def parse_args(self, args: dict[str, Any]) -> BaseModel:
        return self.args_model.model_validate(args)

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "risk": self.risk,
            "args_schema": self.args_model.model_json_schema(),
        }


class ActionRegistry:
    def __init__(self) -> None:
        self._actions: dict[str, ActionSpec] = {}

    def register(
        self,
        name: str,
        description: str,
        risk: RiskLevel,
        args: type[BaseModel] = NoArgs,
    ) -> Callable[[ActionFn], ActionFn]:
        if risk not in RISK_ORDER:
            raise ValueError(f"bad risk level {risk!r}")

        def deco(fn: ActionFn) -> ActionFn:
            if name in self._actions:
                raise ValueError(f"duplicate action {name!r}")
            self._actions[name] = ActionSpec(name, description, risk, args, fn)
            return fn

        return deco

    def get(self, name: str) -> ActionSpec | None:
        return self._actions.get(name)

    def names(self) -> list[str]:
        return sorted(self._actions)

    def catalogue(self) -> list[dict[str, Any]]:
        return [self._actions[n].describe() for n in self.names()]

    def __contains__(self, name: object) -> bool:
        return name in self._actions


class StepSpec(BaseModel):
    """One step of a protocol as stored in `protocols.steps`."""

    model_config = ConfigDict(extra="forbid")

    tool: str = Field(min_length=1, max_length=64)
    args: dict[str, Any] = Field(default_factory=dict)
    on_error: OnError = "stop"


class ProtocolSpec(BaseModel):
    """A protocol definition as the owner submits it (and as built-ins are declared)."""

    model_config = ConfigDict(extra="forbid")

    code: str
    name: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    steps: list[StepSpec] = Field(min_length=1, max_length=MAX_STEPS)
    layout: dict[str, Any] | None = None
    confirm_required: bool = False

    @field_validator("code")
    @classmethod
    def _code(cls, v: str) -> str:
        if not CODE_RE.match(v):
            raise ValueError("code must be lower-case letters, digits and _, 2-48 chars")
        if v in RESERVED_CODES:
            raise ValueError(f"code {v!r} is reserved")
        return v


def _arg_errors(spec: ActionSpec, args: dict[str, Any]) -> list[str]:
    try:
        spec.parse_args(args)
    except ValidationError as exc:
        return [f"{'.'.join(str(p) for p in e['loc']) or 'args'}: {e['msg']}" for e in exc.errors()]
    return []


def validate_steps(
    steps: list[StepSpec], confirm_required: bool, registry: ActionRegistry
) -> list[str]:
    """Every problem with a list of steps, as readable strings; empty when valid."""
    errors: list[str] = []
    for i, step in enumerate(steps, start=1):
        spec = registry.get(step.tool)
        if spec is None:
            errors.append(f"step {i}: unknown action {step.tool!r}")
            continue
        errors.extend(f"step {i} ({step.tool}): {m}" for m in _arg_errors(spec, step.args))
        if spec.risk == "red" and not confirm_required:
            errors.append(
                f"step {i} ({step.tool}): red action; the protocol must set confirm_required"
            )
    return errors


def max_risk(steps: list[StepSpec], registry: ActionRegistry) -> RiskLevel:
    level: RiskLevel = "green"
    for s in steps:
        spec = registry.get(s.tool)
        if spec is not None and RISK_ORDER[spec.risk] > RISK_ORDER[level]:
            level = spec.risk
    return level
