"""The Stage 4 tool catalogue (docs/mark-1-build-plan.md §4.1, docs/tool-server.md).

A thin layer over the protocol action registry (`protocols.actions.REGISTRY`): the registry
owns each action's function, Pydantic argument model and risk level; the catalogue adds what
an external caller (the owner's jarvis) needs to know: a tool name, the domain, an EasyTool
description (one purpose line + one example call), the output schema, the jarvis tier and a
timeout. There is one list of what the platform can do, not two.

Levels and jarvis tiers (plan §2.3, references/sachinx1911-jarvis.md):

    green                                   -> T0  run
    yellow with standing permission         -> T1  run, then report   (paper changes,
                                                                        kill switch ON)
    other yellow                            -> T2  ask the owner first
    red                                     -> never exposed (no tier, not in the catalogue)

The tool server refuses anything above the effective level (the lower of the server
setting TOOL_SERVER_MAX_LEVEL and the token's max_level) and anything not enabled in the
current stage, whatever the caller sends. Stage 4 enables green tools only; the yellow
entries are listed (enabled=False, planned_stage=5) so jarvis can plan for them.

Nothing here places, modifies or cancels an order (CLAUDE.md rules 1-2); there is no red
action in the registry, and a red action could not be registered here.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

import orjson
from pydantic import BaseModel, ConfigDict, Field

from protocols.actions import REGISTRY, collector_status
from protocols.context import ActionContext
from protocols.jsonable import jsonable
from protocols.read_actions import (
    FRESHNESS_VALUES,
    NONE,
    _paper_freshness,
    active_provider,
    combine_freshness,
    provenance,
)
from protocols.registry import RISK_ORDER, ActionRegistry, ActionSpec, RiskLevel

DOMAIN = "trading"
Tier = Literal["T0", "T1", "T2"]
ToolFreshness = Literal["live", "delayed", "stale", "disconnected", "demo", "historical", "none"]
NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,47}$")
DEFAULT_TIMEOUT_S = 10.0
STAGE = 4  # tools with planned_stage > STAGE are listed but not callable

Num = str | float | int | None  # decimals are sent as strings so they stay exact


# ----------------------------------------------------------------------------- outputs
class ToolResult(BaseModel):
    """Every tool output: provenance first (CLAUDE.md rule 5), then a one-line summary.
    Tool-specific fields follow; each tool's model names the main ones."""

    model_config = ConfigDict(extra="allow")

    source: str = Field(min_length=1, description="where the data came from")
    freshness: ToolFreshness = Field(
        description="live | delayed | stale | historical | disconnected | demo, or none when "
        "there is no market source or nothing is stored"
    )
    is_demo: bool = Field(description="true when the data comes from the demo provider")
    summary: str


class _Row(BaseModel):
    model_config = ConfigDict(extra="allow")


class QuoteRow(_Row):
    symbol: str
    status: str
    ltp: Num
    source: str
    freshness: ToolFreshness
    is_demo: bool


class QuoteOut(ToolResult):
    quotes: list[QuoteRow]
    market_open: bool


class CandlesOut(ToolResult):
    symbol: str
    timeframe: str
    status: str
    candles: list[dict[str, Any]]


class ChainOut(ToolResult):
    underlying: str
    status: str
    rows: list[dict[str, Any]]


class OiChangeOut(ToolResult):
    underlying: str
    status: str


class PcrOut(ToolResult):
    pcr: list[dict[str, Any]]
    thresholds: dict[str, Any]


class RegimeOut(ToolResult):
    regimes: list[dict[str, Any]]


class BreadthOut(ToolResult):
    universe: str
    status: str


class ScannerOut(ToolResult):
    status: str
    rows: list[dict[str, Any]]
    total: int


class BacktestOut(ToolResult):
    status: str


class PaperPositionsOut(ToolResult):
    mode: Literal["paper"]
    positions: list[dict[str, Any]]


class PaperPnlOut(ToolResult):
    mode: Literal["paper"]
    period: str
    accounts: list[dict[str, Any]]


class PaperStatusOut(ToolResult):
    accounts: list[dict[str, Any]]


class HealthOut(ToolResult):
    status: str
    market_open: bool
    problems: list[str]


class BrokerSessionsOut(ToolResult):
    brokers: list[dict[str, Any]]


class AlertsOut(ToolResult):
    alerts: list[dict[str, Any]]


class EventsOut(ToolResult):
    date: str
    events: list[dict[str, Any]]


class ReportOut(ToolResult):
    status: str


class NewsOut(ToolResult):
    items: list[dict[str, Any]]


class ProtocolStatusOut(ToolResult):
    runs: list[dict[str, Any]]


class OwnerRulesOut(ToolResult):
    rules: list[dict[str, Any]]


class KillSwitchOut(ToolResult):
    scope: str
    active: bool


class StopPaperOut(ToolResult):
    stopped: list[dict[str, Any]]


class ClosePaperOut(ToolResult):
    positions: list[dict[str, Any]]


# ----------------------------------------------------------------------------- provenance
# Stage 3 actions predate the tool server and do not carry provenance themselves; these add it.
Provenance = Callable[[ActionContext, dict[str, Any]], Awaitable[dict[str, Any]]]


async def _prov_health(ctx: ActionContext, r: dict[str, Any]) -> dict[str, Any]:
    demo = bool(r.get("collector", {}).get("is_demo"))
    return provenance("platform process health (no market source)", NONE, demo)


async def _prov_platform(ctx: ActionContext, r: dict[str, Any]) -> dict[str, Any]:
    return provenance("platform state (no market source)", NONE, False)


async def _prov_events(ctx: ActionContext, r: dict[str, Any]) -> dict[str, Any]:
    return provenance("events calendar (no market source)", NONE, False)


async def _prov_regime(ctx: ActionContext, r: dict[str, Any]) -> dict[str, Any]:
    provider, demo = await active_provider(ctx)
    have = any(x.get("daily") for x in r.get("regimes", []))
    fresh = ("demo" if demo else "historical") if have else NONE
    return provenance(f"regime_daily (derived from {provider} daily candles)", fresh, demo)


async def _prov_pcr(ctx: ActionContext, r: dict[str, Any]) -> dict[str, Any]:
    rows = [x for x in r.get("pcr", []) if x.get("pcr") is not None]
    provider, provider_demo = await active_provider(ctx)
    if not rows:
        return provenance(provider, NONE, provider_demo)
    demo = any(bool(x.get("is_demo")) for x in rows)
    fresh = combine_freshness(
        "demo" if x.get("is_demo") else ("delayed" if x.get("freshness") == "fresh" else "stale")
        for x in rows
    )
    sources = sorted({str(x.get("source") or provider) for x in rows})
    return provenance(",".join(sources), fresh, demo)


async def _prov_paper(ctx: ActionContext, r: dict[str, Any]) -> dict[str, Any]:
    provider, demo = await active_provider(ctx)
    fresh, _note = await _paper_freshness(ctx, demo)
    return provenance(
        f"paper accounts ({provider} marks)", fresh if r.get("accounts") else NONE, demo
    )


async def _prov_alerts(ctx: ActionContext, r: dict[str, Any]) -> dict[str, Any]:
    provider, demo = await active_provider(ctx)
    return provenance(f"alerts (stored; raised from {provider} data)", NONE, demo)


async def _prov_kill(ctx: ActionContext, r: dict[str, Any]) -> dict[str, Any]:
    return provenance("risk kill switch (no market source)", NONE, False)


async def _prov_collector_demo(ctx: ActionContext, r: dict[str, Any]) -> dict[str, Any]:
    now = ctx.now()
    c = await collector_status(ctx, now, False)
    return provenance("paper trader (no market source)", NONE, bool(c.get("is_demo")))


# ----------------------------------------------------------------------------- specs
def tier_for(level: RiskLevel, standing_permission: bool) -> Tier | None:
    if level == "green":
        return "T0"
    if level == "yellow":
        return "T1" if standing_permission else "T2"
    return None  # red: never exposed


def level_allows(limit: str, level: str) -> bool:
    """True when `level` is at or below `limit`. Red is never allowed, whatever the limit."""
    if level not in RISK_ORDER or limit not in RISK_ORDER or level == "red":
        return False
    return RISK_ORDER[level] <= RISK_ORDER[limit]


def effective_level(*limits: str) -> str:
    """The lowest of the given limits (unknown values count as green); never above yellow."""
    known = [lim if lim in RISK_ORDER else "green" for lim in limits] or ["green"]
    low = min(known, key=lambda x: RISK_ORDER[x])
    return "yellow" if low == "red" else low


@dataclass(frozen=True)
class ToolSpec:
    name: str
    action: str  # name in the protocol action registry
    purpose: str  # one line: what the tool is for
    example: dict[str, Any]  # one example call's arguments
    output_model: type[ToolResult]
    timeout_s: float = DEFAULT_TIMEOUT_S
    standing_permission: bool = False  # yellow only: paper changes / kill switch ON (T1)
    planned_stage: int = STAGE
    writes: bool = False  # the server commits the session only for these
    provenance: Provenance | None = None
    domain: str = DOMAIN
    registry: ActionRegistry = field(default=REGISTRY, repr=False, compare=False)

    @property
    def action_spec(self) -> ActionSpec:
        spec = self.registry.get(self.action)
        if spec is None:
            raise LookupError(f"tool {self.name!r}: action {self.action!r} is not registered")
        return spec

    @property
    def level(self) -> RiskLevel:
        return self.action_spec.risk

    @property
    def tier(self) -> Tier | None:
        return tier_for(self.level, self.standing_permission)

    @property
    def enabled(self) -> bool:
        return self.planned_stage <= STAGE and self.level != "red"

    @property
    def description(self) -> str:
        ex = orjson.dumps(self.example).decode()
        return f"{self.purpose} Example: {self.name}({ex})"

    def input_schema(self) -> dict[str, Any]:
        return self.action_spec.args_model.model_json_schema()

    def output_schema(self) -> dict[str, Any]:
        return self.output_model.model_json_schema()

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "domain": self.domain,
            "description": self.description,
            "level": self.level,
            "tier": self.tier,
            "timeout_s": self.timeout_s,
            "enabled": self.enabled,
            "planned_stage": self.planned_stage,
            "input_schema": self.input_schema(),
            "output_schema": self.output_schema(),
        }

    def callable_at(self, limit: str) -> bool:
        return self.enabled and level_allows(limit, self.level)


class ToolCatalogue:
    def __init__(self, registry: ActionRegistry = REGISTRY) -> None:
        self.registry = registry
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> ToolSpec:
        if not NAME_RE.match(spec.name):
            raise ValueError(f"bad tool name {spec.name!r}")
        if spec.name in self._tools:
            raise ValueError(f"duplicate tool {spec.name!r}")
        if spec.registry is not self.registry:
            raise ValueError(f"tool {spec.name!r} uses a different action registry")
        if spec.level == "red":
            raise ValueError(
                f"tool {spec.name!r}: red actions are never exposed to the tool server"
            )
        if spec.timeout_s <= 0 or spec.timeout_s > 120:
            raise ValueError(f"tool {spec.name!r}: timeout must be in (0, 120] s")
        if spec.level == "green" and spec.standing_permission:
            raise ValueError(f"tool {spec.name!r}: standing permission is for yellow tools")
        self._tools[spec.name] = spec
        return spec

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def all(self) -> list[ToolSpec]:
        return [self._tools[n] for n in sorted(self._tools)]

    def callable_at(self, limit: str) -> list[ToolSpec]:
        return [t for t in self.all() if t.callable_at(limit)]

    def actions_covered(self) -> set[str]:
        return {t.action for t in self._tools.values()}

    def __contains__(self, name: object) -> bool:
        return name in self._tools


async def run_tool(spec: ToolSpec, ctx: ActionContext, args: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the arguments with the action's model, run the action, add provenance when the
    action does not carry it, and check the result against the tool's output model. Raises
    `pydantic.ValidationError` for bad arguments and `ActionError` for refusals of the action."""
    action = spec.action_spec
    parsed = action.parse_args(dict(args))
    result = await action.fn(ctx, parsed)
    if spec.provenance is not None:
        prov = await spec.provenance(ctx, result)
        result = {**prov, **{k: v for k, v in result.items() if k not in prov}}
    out = spec.output_model.model_validate(jsonable(result))
    data = out.model_dump(mode="json")
    if data["freshness"] not in FRESHNESS_VALUES:  # pragma: no cover - Literal guards it
        raise ValueError("bad freshness")
    return data


# ----------------------------------------------------------------------------- the catalogue
CATALOGUE = ToolCatalogue()


def register_tool(spec: ToolSpec) -> ToolSpec:
    """Add a tool to the catalogue the tool server serves.

    Hook for the accuracy loop (Mark 1 Stage 4.6): `record_view` (JARVIS states a market view;
    the tool server stores it with our reference price in `ai_observations`) is owned by that
    work. To expose it, register a green action `record_view` in `REGISTRY` whose function
    calls the record_view service (it appends one measurement row and has no trading effect),
    then call:

        register_tool(ToolSpec(
            name="record_view", action="record_view", writes=True,
            purpose="Record a stated market view so it can be scored later.",
            example={"symbol": "NIFTY", "direction": "up", "horizon_days": 5, ...},
            output_model=<its ToolResult subclass>,
        ))

    from a module imported by `protocols/__init__.py`. `writes=True` makes the tool server
    commit that call's session; every other green tool's session is rolled back.
    """
    return CATALOGUE.register(spec)


_G = [
    ToolSpec(
        "quote",
        "quote",
        "Latest quote per symbol with its freshness; disconnected (with reason and last stored "
        "close) when the collector has no live quote.",
        {"symbols": ["NIFTY", "BANKNIFTY"]},
        QuoteOut,
        timeout_s=8,
    ),
    ToolSpec(
        "candles",
        "candles",
        "Last N stored OHLCV candles of one symbol and timeframe from the active provider.",
        {"symbol": "NIFTY", "timeframe": "5m", "limit": 50},
        CandlesOut,
    ),
    ToolSpec(
        "option_chain",
        "option_chain",
        "Newest stored option chain of an underlying and expiry around the ATM strike.",
        {"underlying": "NIFTY", "expiry": "2026-11-25", "strikes_around_atm": 5},
        ChainOut,
    ),
    ToolSpec(
        "oi_change",
        "oi_change",
        "Per-strike call/put OI change between two IST times of one trading day.",
        {"underlying": "BANKNIFTY", "start": "09:15", "end": "11:00"},
        OiChangeOut,
    ),
    ToolSpec(
        "greeks",
        "greeks",
        "IV and Greeks per strike as the provider sent them, newest or as of a time.",
        {"underlying": "NIFTY", "strikes_around_atm": 3},
        ChainOut,
    ),
    ToolSpec(
        "pcr",
        "pcr_now",
        "Put/call ratio by OI from the newest chain, against the owner's pcr_guard thresholds.",
        {"symbols": ["NIFTY"]},
        PcrOut,
        provenance=_prov_pcr,
    ),
    ToolSpec(
        "regime",
        "regime_summary",
        "Stored daily market regime (trend, strength, volatility, structure) and today's day type.",
        {"symbols": ["NIFTY", "BANKNIFTY"]},
        RegimeOut,
        provenance=_prov_regime,
    ),
    ToolSpec(
        "breadth",
        "breadth",
        "Stored daily market breadth (advances/declines, 52w highs/lows, % above EMAs).",
        {"universe": "NIFTY50"},
        BreadthOut,
    ),
    ToolSpec(
        "scanner_run",
        "scanner_run",
        "Run a preset or ad-hoc scan over the latest stored nightly scanner snapshot.",
        {"preset": "Top gainers", "limit": 10},
        ScannerOut,
        timeout_s=15,
    ),
    ToolSpec(
        "backtest_results",
        "backtest_results",
        "Recent backtest jobs with headline metrics, or one job's metrics and assumptions.",
        {"limit": 5},
        BacktestOut,
    ),
    ToolSpec(
        "paper_positions",
        "paper_positions",
        "Open paper positions with average, last price and unrealised P&L.",
        {},
        PaperPositionsOut,
    ),
    ToolSpec(
        "paper_pnl",
        "paper_pnl",
        "Paper realised P&L for a day, week, month or custom period, plus open P&L.",
        {"period": "week"},
        PaperPnlOut,
    ),
    ToolSpec(
        "paper_status",
        "paper_status",
        "Paper accounts at a glance: cash, positions, day P&L, running strategies, halts.",
        {},
        PaperStatusOut,
        provenance=_prov_paper,
    ),
    ToolSpec(
        "health",
        "health_check",
        "State of every platform process and broker session in one answer.",
        {},
        HealthOut,
        provenance=_prov_health,
    ),
    ToolSpec(
        "broker_sessions",
        "broker_sessions",
        "Daily broker session per broker (valid, expired, missing) with expiry; no secrets.",
        {},
        BrokerSessionsOut,
        provenance=_prov_platform,
    ),
    ToolSpec(
        "alerts",
        "recent_alerts",
        "Stored alerts of the last N hours, newest first, optionally unacknowledged only.",
        {"hours": 24, "unacknowledged_only": True},
        AlertsOut,
        provenance=_prov_alerts,
    ),
    ToolSpec(
        "events_today",
        "todays_events",
        "Market events stored for today (RBI, Fed, budget, expiry, results) and trading blocks.",
        {},
        EventsOut,
        provenance=_prov_events,
    ),
    ToolSpec(
        "daily_report",
        "daily_report",
        "The stored evening brief / end-of-day report, latest or for one date.",
        {"day": "2026-11-20"},
        ReportOut,
    ),
    ToolSpec(
        "news",
        "news",
        "Recent raw news headlines, optionally only those tagged with one symbol.",
        {"symbol": "RELIANCE", "hours": 24, "limit": 10},
        NewsOut,
    ),
    ToolSpec(
        "protocol_status",
        "protocol_status",
        "Recent protocol runs with status, summary and step outcomes.",
        {"limit": 5},
        ProtocolStatusOut,
    ),
    ToolSpec(
        "owner_rules",
        "owner_rules",
        "The owner's hard trading rules and their thresholds (they cannot be bypassed).",
        {},
        OwnerRulesOut,
    ),
]

# Yellow: listed for planning, not callable until Stage 5 (planned_stage=5). A jarvis "/stop"
# or "Clean Slate" maps to kill_switch_on, which only ever turns trading OFF; turning the kill
# switch off is red and stays with the owner in the web UI.
_Y = [
    ToolSpec(
        "kill_switch_on",
        "kill_switch_on",
        "Engage the kill switch: every new entry is blocked at once (never turns it off).",
        {"scope": "global", "reason": "owner said stop"},
        KillSwitchOut,
        standing_permission=True,  # plan §2.3: turning the kill switch ON is always immediate
        planned_stage=5,
        writes=True,
        provenance=_prov_kill,
    ),
    ToolSpec(
        "stop_paper_strategies",
        "stop_paper_strategies",
        "Stop every running paper strategy, optionally squaring off its positions.",
        {"reason": "owner said stop paper", "flatten": True},
        StopPaperOut,
        standing_permission=True,  # paper change: owner's standing permission (plan §2.3)
        planned_stage=5,
        writes=True,
        provenance=_prov_collector_demo,
    ),
    ToolSpec(
        "close_paper_positions",
        "close_paper_positions",
        "Request a square-off of every open paper position through the paper trader.",
        {"reason": "owner said close paper positions"},
        ClosePaperOut,
        standing_permission=True,
        planned_stage=5,
        writes=True,
        provenance=_prov_collector_demo,
    ),
]

for _spec in (*_G, *_Y):
    CATALOGUE.register(_spec)
