"""Extraction → DSL compiler: deterministic, transparent about defaults, honest about gaps."""

from __future__ import annotations

from typing import Any

from ai.nl_builder import NLExtraction, compile_extraction
from strategy.dsl import StrategyDocument, validate_document

MR_TEXT = "EMA 9 ने EMA 21 ला वरच्या बाजूने cross केल्यावर आणि RSI 55 पेक्षा जास्त असल्यास Buy करा."


def ind(type_: str, period: int | None = None, **kw: Any) -> dict[str, Any]:
    return {"kind": "indicator", "indicator": {"type": type_, "period": period, **kw}}


def num(v: float) -> dict[str, Any]:
    return {"kind": "number", "number": v}


def cond(
    phrase: str, left: dict[str, Any], cmp: str, right: dict[str, Any] | None = None, **kw: Any
) -> dict[str, Any]:
    return {"original_phrase": phrase, "left": left, "comparison": cmp, "right": right, **kw}


def marathi_extraction() -> NLExtraction:
    return NLExtraction.model_validate(
        {
            "strategy_name": "NIFTY EMA Momentum",
            "detected_language": "mr",
            "direction": "long_only",
            "entry_long": {
                "op": "and",
                "conditions": [
                    cond(
                        "EMA 9 ने EMA 21 ला वरच्या बाजूने cross केल्यावर",
                        ind("EMA", 9),
                        "crosses_above",
                        ind("EMA", 21),
                    ),
                    cond("RSI 55 पेक्षा जास्त असल्यास", ind("RSI"), "greater_than", num(55)),
                ],
            },
            "clarification_questions": [
                {
                    "id": "q1",
                    "field": "exit_conditions",
                    "question_local": "Exit कधी करायचा?",
                    "question_en": "When should the position exit?",
                }
            ],
        }
    )


def mr_with(**over: Any) -> NLExtraction:
    d = marathi_extraction().model_dump()
    d.update(over)
    return NLExtraction.model_validate(d)


def compile_mr(ex: NLExtraction | None = None, **kw: Any) -> Any:
    params: dict[str, Any] = {
        "market": "NSE",
        "instrument": "NIFTY",
        "timeframe": "5m",
        "original_text": MR_TEXT,
    }
    params.update(kw)
    return compile_extraction(ex or marathi_extraction(), **params)


def test_master_prompt_example_compiles_to_the_documented_draft() -> None:
    res = compile_mr()
    assert res.errors == []
    doc = StrategyDocument.model_validate(res.dsl)
    rep = validate_document(doc, "draft")
    assert rep.errors == []
    # DSL doc §10.1: the draft before answers lists exactly these.
    assert set(rep.missing_information) == {
        "Exit condition",
        "Stop loss",
        "Target",
        "Position sizing",
        "Product/square-off",
    }
    d = res.dsl
    assert d["origin"] == "user_nl" and d["language"] == "mr" and d["original_text"] == MR_TEXT
    assert d["universe"] == {
        "kind": "underlying_future",
        "underlying": "NIFTY",
        "contract": {"expiry": "current_month"},
    }
    assert d["indicators"] == {
        "ema_9": {"type": "EMA", "params": {"period": 9}},
        "ema_21": {"type": "EMA", "params": {"period": 21}},
        "rsi_14": {"type": "RSI", "params": {"period": 14}},
    }
    assert d["entry"]["long"] == {
        "kind": "group",
        "op": "and",
        "conditions": [
            {
                "kind": "cross",
                "left": {"kind": "indicator", "id": "ema_9"},
                "direction": "crosses_above",
                "right": {"kind": "indicator", "id": "ema_21"},
            },
            {
                "kind": "compare",
                "left": {"kind": "indicator", "id": "rsi_14"},
                "op": "gt",
                "right": {"kind": "const", "value": 55},
            },
        ],
    }
    assert (
        d["exit"] is None
        and d["stop_loss"] is None
        and d["target"] is None
        and d["position_sizing"] is None
    )
    assert d["session"] == {"product": "INTRADAY"}
    # Nothing was filled in silently: every default is listed.
    assert any("RSI period 14" in s for s in res.defaults_applied)
    assert any("session.product=INTRADAY" in s for s in res.defaults_applied)
    assert any("current-month future" in s for s in res.defaults_applied)


def test_same_extraction_same_dsl() -> None:
    assert compile_mr().dsl == compile_mr().dsl


def test_ema_without_period_is_an_error_not_a_guess() -> None:
    ex = mr_with(
        **{
            "entry_long": {
                "op": "and",
                "conditions": [
                    cond(
                        "EMA वर गेला",
                        {"kind": "price", "price": "close"},
                        "greater_than",
                        ind("EMA"),
                    )
                ],
            }
        }
    )
    res = compile_mr(ex)
    assert res.errors and "EMA needs 'period'" in res.errors[0]
    assert res.dsl["entry"] is None  # the unusable condition is not half-compiled


def test_multi_output_indicator_needs_a_named_output() -> None:
    ex = mr_with(
        **{
            "entry_long": {
                "op": "and",
                "conditions": [
                    cond(
                        "close above bollinger",
                        {"kind": "price", "price": "close"},
                        "greater_than",
                        ind("BOLLINGER", 20),
                    ),
                    cond(
                        "close above upper band",
                        {"kind": "price", "price": "close"},
                        "greater_than",
                        ind("BOLLINGER", 20, output="upper"),
                    ),
                ],
            }
        }
    )
    res = compile_mr(ex)
    assert len(res.errors) == 1 and "which one is not stated" in res.errors[0]
    # The explicit one compiled, with the library's std default listed, not hidden.
    assert res.dsl["entry"]["long"]["right"] == {
        "kind": "indicator",
        "id": "bollinger_20_2",
        "field": "upper",
    }
    assert any("BOLLINGER.std=2" in s for s in res.defaults_applied)


def test_levels_sizing_between_and_slope() -> None:
    ex = mr_with(
        **{
            "entry_short": {
                "op": "or",
                "conditions": [
                    cond(
                        "RSI 30 आणि 70 च्या मध्ये",
                        ind("RSI", 14),
                        "between",
                        None,
                        low=num(30),
                        high=num(70),
                    ),
                    cond("ADX वाढतोय", ind("ADX"), "rising"),
                ],
            },
            "direction": None,
            "stop_loss": {"original_phrase": "1.5 ATR stop", "unit": "atr", "value": 1.5},
            "target": {"original_phrase": "1:2 risk reward", "unit": "rr", "value": 2},
            "position_sizing": {"original_phrase": "2 lots", "method": "fixed_lots", "value": 2},
            "session": {"product": "INTRADAY", "square_off_at": "15:15"},
            "max_trades_per_day": 3,
        }
    )
    res = compile_mr(ex)
    assert res.errors == []
    d = res.dsl
    assert d["direction"] == "both" and any("inferred" in s for s in res.defaults_applied)
    assert d["entry"]["short"]["op"] == "or"
    assert d["entry"]["short"]["conditions"][0]["kind"] == "between"
    assert d["entry"]["short"]["conditions"][1] == {
        "kind": "slope",
        "value": {"kind": "indicator", "id": "adx_14"},
        "direction": "rising",
        "bars": 1,
    }
    assert d["stop_loss"] == {"unit": "atr", "value": 1.5, "atr_indicator_id": "atr_14"}
    assert d["indicators"]["atr_14"] == {"type": "ATR", "params": {"period": 14}}
    assert d["target"] == {"rr_multiple": 2.0}
    assert d["position_sizing"] == {"method": "fixed_lots", "lots": 2}
    assert (
        d["session"] == {"product": "INTRADAY", "square_off_at": "15:15"}
        and d["max_trades_per_day"] == 3
    )
    doc = StrategyDocument.model_validate(d)
    rep = validate_document(doc, "draft")
    assert rep.errors == [] and rep.missing_information == []


def test_bad_values_are_errors() -> None:
    ex = mr_with(
        **{
            "stop_loss": {"original_phrase": "2R stop", "unit": "rr", "value": 2},
            "position_sizing": {
                "original_phrase": "1.5 lots",
                "method": "fixed_lots",
                "value": 1.5,
            },
            "timeframe": "15m",
        }
    )
    res = compile_mr(ex)
    assert any("risk-reward multiple only makes sense for the target" in e for e in res.errors)
    assert any("whole number" in e for e in res.errors)
    assert res.dsl["stop_loss"] is None and res.dsl["position_sizing"] is None
    assert any("description says 15m" in w for w in res.warnings)


def test_non_index_instrument_uses_resolved_ids_or_stays_empty() -> None:
    res = compile_mr(instrument="RELIANCE", instrument_ids=["42"])
    assert res.dsl["universe"] == {"kind": "instrument", "instrument_ids": ["42"]}
    res = compile_mr(instrument="RELIANCE")
    assert res.dsl["universe"] == {"kind": "instrument", "instrument_ids": []}
    rep = validate_document(StrategyDocument.model_validate(res.dsl), "draft")
    assert any("instrument_ids" in e for e in rep.errors)  # cannot be saved until resolved
