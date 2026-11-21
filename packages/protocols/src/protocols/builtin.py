"""Built-in trading protocols (docs/mark-1-plan.md §2.4). Seeded idempotently: a change to a
definition here bumps the stored version on the next seed."""

from __future__ import annotations

from protocols.registry import ProtocolSpec, StepSpec


def _s(tool: str, on_error: str = "continue", **args: object) -> StepSpec:
    return StepSpec.model_validate({"tool": tool, "args": args, "on_error": on_error})


BUILTINS: list[ProtocolSpec] = [
    ProtocolSpec(
        code="market_open",
        name="Market Open",
        description="Broker session, feed and processes; yesterday's regime, PCR now and "
        "today's events.",
        steps=[
            _s("health_check"),
            _s("broker_sessions"),
            _s("regime_summary"),
            _s("pcr_now"),
            _s("todays_events"),
        ],
    ),
    ProtocolSpec(
        code="market_close",
        name="Market Close",
        description="Paper positions and day P&L, closing PCR, the day's alerts, process "
        "health for tomorrow.",
        steps=[_s("paper_status"), _s("pcr_now"), _s("recent_alerts"), _s("health_check")],
    ),
    ProtocolSpec(
        code="shutdown",
        name="Shutdown",
        description="Stops every paper strategy and squares off paper positions. Asks first.",
        steps=[
            _s("stop_paper_strategies", on_error="stop"),
            _s("close_paper_positions"),
            _s("paper_status"),
        ],
        confirm_required=True,
    ),
    ProtocolSpec(
        code="clean_slate",
        name="Clean Slate",
        description="Kill switch ON at once: every new entry is blocked. Immediate, no "
        "confirmation (turning it off stays with the owner).",
        steps=[_s("kill_switch_on"), _s("paper_status")],
    ),
    ProtocolSpec(
        code="health_check",
        name="Health Check",
        description="State of every process in one answer.",
        steps=[_s("health_check", on_error="stop")],
    ),
    ProtocolSpec(
        code="review",
        name="Review",
        description="Day's paper results and alerts. The full trade review arrives with "
        "reports (Stage 3.3).",
        steps=[_s("paper_status"), _s("recent_alerts")],
    ),
]

BUILTIN_CODES = frozenset(p.code for p in BUILTINS)
