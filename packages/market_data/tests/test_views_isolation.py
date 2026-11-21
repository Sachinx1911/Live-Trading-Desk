"""Observations measure JARVIS and never feed trading (ADR-009, Mark 1 Stage 4.6).

The import-linter contract "AI views never feed trading" forbids strategy, risk, execution,
backtest and the paper trader from importing market_data.views. This test also catches a
direct read of the tables through the ORM model or raw SQL in those packages."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TRADING_SOURCES = [
    ROOT / "packages" / "strategy" / "src",
    ROOT / "packages" / "risk" / "src",
    ROOT / "packages" / "execution" / "src",
    ROOT / "packages" / "backtest" / "src",
    ROOT / "apps" / "trader" / "src",
]
NEEDLE = re.compile(r"AiObservation|AiViewScore|ai_observations|ai_view_scores|market_data\.views")


def test_trading_code_never_reads_views() -> None:
    hits = [
        f"{p.relative_to(ROOT)}"
        for src in TRADING_SOURCES
        for p in src.rglob("*.py")
        if NEEDLE.search(p.read_text(encoding="utf-8"))
    ]
    assert hits == []
    assert all(src.is_dir() for src in TRADING_SOURCES)
