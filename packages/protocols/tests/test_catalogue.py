"""The Stage 4 tool catalogue over the protocol action registry (no DB)."""

from __future__ import annotations

from typing import get_args

import pytest
from pydantic import ValidationError

from core.models import Freshness
from protocols import REGISTRY
from protocols.catalogue import (
    CATALOGUE,
    STAGE,
    ToolFreshness,
    ToolResult,
    tier_for,
)
from protocols.read_actions import FRESHNESS_VALUES, combine_freshness, provenance

STAGE4_GREEN = {
    "quote",
    "candles",
    "option_chain",
    "oi_change",
    "greeks",
    "pcr",
    "regime",
    "breadth",
    "scanner_run",
    "backtest_results",
    "paper_positions",
    "paper_pnl",
    "health",
    "alerts",
    "daily_report",
    "news",
    "protocol_status",
    "owner_rules",
}


def test_every_registry_action_is_catalogued_once_and_none_is_red() -> None:
    assert CATALOGUE.actions_covered() == set(REGISTRY.names())
    for t in CATALOGUE.all():
        assert t.level in ("green", "yellow")
        assert t.domain == "trading"


def test_required_green_tools_are_enabled_at_t0() -> None:
    names = {t.name for t in CATALOGUE.callable_at("green")}
    assert names >= STAGE4_GREEN
    for n in STAGE4_GREEN:
        t = CATALOGUE.get(n)
        assert t is not None and t.level == "green" and t.tier == "T0" and t.enabled


def test_yellow_tools_are_listed_for_stage_5_only() -> None:
    yellow = [t for t in CATALOGUE.all() if t.level == "yellow"]
    assert {t.name for t in yellow} == {
        "kill_switch_on",
        "stop_paper_strategies",
        "close_paper_positions",
    }
    for t in yellow:
        assert not t.enabled and t.planned_stage == STAGE + 1
        assert not t.callable_at("yellow")
        assert t.tier == "T1"  # paper standing permission / kill switch ON is immediate


def test_tier_mapping() -> None:
    assert tier_for("green", False) == "T0"
    assert tier_for("yellow", True) == "T1"
    assert tier_for("yellow", False) == "T2"
    assert tier_for("red", True) is None


@pytest.mark.parametrize("tool", CATALOGUE.all(), ids=lambda t: t.name)
def test_contract_shape(tool) -> None:  # type: ignore[no-untyped-def]
    d = tool.describe()
    assert d["description"].count("Example: ") == 1
    assert d["input_schema"]["type"] == "object"
    out = d["output_schema"]
    assert {"source", "freshness", "is_demo", "summary"} <= set(out["required"])
    assert 0 < d["timeout_s"] <= 120
    # The documented example is a valid call.
    tool.action_spec.parse_args(tool.example)


@pytest.mark.parametrize("tool", CATALOGUE.all(), ids=lambda t: t.name)
def test_input_schema_rejects_unknown_arguments(tool) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValidationError):
        tool.action_spec.parse_args({**tool.example, "exec": "rm -rf /"})


def test_freshness_values_are_the_enum_plus_none() -> None:
    assert set(get_args(ToolFreshness)) == {f.value for f in Freshness} | {"none"}
    assert set(FRESHNESS_VALUES) == set(get_args(ToolFreshness))
    with pytest.raises(ValueError):
        provenance("x", "fresh", False)


def test_output_without_provenance_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ToolResult.model_validate({"summary": "no provenance"})
    with pytest.raises(ValidationError):
        ToolResult.model_validate(
            {"summary": "s", "source": "x", "freshness": "fresh", "is_demo": False}
        )


def test_combine_freshness_demo_wins_then_worst() -> None:
    assert combine_freshness([]) == "none"
    assert combine_freshness(["live", "demo"]) == "demo"
    assert combine_freshness(["live", "delayed"]) == "delayed"
    assert combine_freshness(["live", "disconnected", "historical"]) == "disconnected"
    assert combine_freshness(["none", "disconnected"]) == "disconnected"
    assert combine_freshness(["none"]) == "none"


def test_no_tool_names_an_order_or_live_path() -> None:
    for t in CATALOGUE.all():
        assert "order" not in t.name and "live" not in t.name
        assert "kill_switch_off" != t.name
