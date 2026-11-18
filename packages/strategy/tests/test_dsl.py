import json

import pytest
from pydantic import ValidationError

from strategy.dsl.examples import example_names, load_example
from strategy.dsl.json_schema import json_schema
from strategy.dsl.schema import StrategyDocument
from strategy.dsl.validate import validate_document


@pytest.mark.parametrize("name", example_names())
def test_examples_round_trip(name: str) -> None:
    raw = load_example(name)
    doc = StrategyDocument.model_validate(raw)
    dumped = doc.model_dump(mode="json", exclude_none=True)
    again = StrategyDocument.model_validate(dumped)
    assert again == doc
    # the examples are complete documents: no errors for validated status
    rep = validate_document(doc, "validated")
    assert rep.errors == [], rep.errors


def test_json_schema_exports_and_is_json() -> None:
    schema = json_schema()
    assert schema["title"].startswith("StrategyDSL")
    assert "dsl_schema_version" in schema["properties"]
    json.dumps(schema)


def test_unknown_field_rejected() -> None:
    raw = load_example("ema_rsi_nifty")
    raw["surprise"] = 1
    with pytest.raises(ValidationError):
        StrategyDocument.model_validate(raw)


def test_negative_offset_rejected() -> None:
    raw = load_example("ema_rsi_nifty")
    raw["entry"]["long"]["conditions"][1]["left"]["offset"] = -1
    with pytest.raises(ValidationError):
        StrategyDocument.model_validate(raw)


def test_undeclared_indicator_is_error() -> None:
    raw = load_example("ema_rsi_nifty")
    raw["entry"]["long"]["conditions"][1]["left"]["id"] = "rsi99"
    rep = validate_document(StrategyDocument.model_validate(raw))
    assert any("rsi99" in e for e in rep.errors)


def test_bad_field_is_error() -> None:
    raw = load_example("ema_rsi_nifty")
    raw["entry"]["long"]["conditions"][1]["left"]["field"] = "upper"
    rep = validate_document(StrategyDocument.model_validate(raw))
    assert any("no field 'upper'" in e for e in rep.errors)


def test_intraday_without_square_off() -> None:
    raw = load_example("ema_rsi_nifty")
    raw["session"]["square_off_at"] = None
    doc = StrategyDocument.model_validate(raw)
    assert "Product/square-off" in validate_document(doc, "draft").missing_information
    assert any("square_off_at" in e for e in validate_document(doc, "validated").errors)


def test_draft_lists_missing_information() -> None:
    raw = load_example("ema_rsi_nifty")
    for k in ("exit", "stop_loss", "target", "position_sizing"):
        raw[k] = None
    rep = validate_document(StrategyDocument.model_validate(raw), "draft")
    assert rep.errors == []
    assert {"Exit condition", "Stop loss", "Target", "Position sizing"} <= set(
        rep.missing_information
    )


def test_live_readiness_requires_stop_and_caps() -> None:
    raw = load_example("ema_rsi_nifty")
    raw["stop_loss"] = None
    raw["max_trades_per_day"] = None
    raw["position_sizing"] = {"method": "fixed_lots", "lots": 1}
    rep = validate_document(StrategyDocument.model_validate(raw), "approved_live")
    assert any("stop_loss" in e for e in rep.errors)
    assert any("max_trades_per_day" in e for e in rep.errors)
    assert any("max_lots" in e for e in rep.errors)


def test_direction_consistency_and_risk_percent_needs_stop() -> None:
    raw = load_example("ema_rsi_nifty")
    raw["direction"] = "both"
    raw["stop_loss"] = None
    raw["position_sizing"] = {"method": "risk_percent", "risk_percent": 1}
    rep = validate_document(StrategyDocument.model_validate(raw))
    assert any("entry.short required" in e for e in rep.errors)
    assert any("risk_percent requires stop_loss" in e for e in rep.errors)


def test_context_timeframe_must_be_declared() -> None:
    raw = load_example("banknifty_vwap_reversion")
    raw["context_timeframes"] = []
    rep = validate_document(StrategyDocument.model_validate(raw))
    assert any("context_timeframes" in e for e in rep.errors)


def test_overfitting_warning() -> None:
    rep = validate_document(StrategyDocument.model_validate(load_example("nifty50_daily_breakout")))
    assert any("tunable" in w for w in rep.warnings)
