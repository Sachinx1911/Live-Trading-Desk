"""Shared fixture data for the NL builder tests (the master prompt's Marathi example)."""

from __future__ import annotations

from typing import Any

MR_TEXT = "EMA 9 ने EMA 21 ला वरच्या बाजूने cross केल्यावर आणि RSI 55 पेक्षा जास्त असल्यास Buy करा."


def marathi_extraction_dict() -> dict[str, Any]:
    return {
        "strategy_name": "NIFTY EMA Momentum",
        "detected_language": "mr",
        "direction": "long_only",
        "timeframe": None,
        "entry_long": {
            "op": "and",
            "conditions": [
                {
                    "original_phrase": "EMA 9 ने EMA 21 ला वरच्या बाजूने cross केल्यावर",
                    "left": {"kind": "indicator", "indicator": {"type": "EMA", "period": 9}},
                    "comparison": "crosses_above",
                    "right": {"kind": "indicator", "indicator": {"type": "EMA", "period": 21}},
                },
                {
                    "original_phrase": "RSI 55 पेक्षा जास्त असल्यास",
                    "left": {"kind": "indicator", "indicator": {"type": "RSI"}},
                    "comparison": "greater_than",
                    "right": {"kind": "number", "number": 55},
                },
            ],
        },
        "entry_short": None,
        "exit_long": None,
        "exit_short": None,
        "stop_loss": None,
        "target": None,
        "position_sizing": None,
        "session": None,
        "max_trades_per_day": None,
        "unsupported": [],
        "clarification_questions": [
            {
                "id": "q1",
                "field": "exit_conditions",
                "question_local": "Exit कधी करायचा?",
                "question_en": "When should the position exit?",
            }
        ],
    }
