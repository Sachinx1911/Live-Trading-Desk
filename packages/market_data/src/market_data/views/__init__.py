"""JARVIS accuracy loop (Mark 1 Stage 4.6): record directional views with an honest reference
price, grade them after their horizon, report hit-rates. No LLM runs here.

Observations measure JARVIS, nothing more: no strategy, risk check, backtest, order path or
the paper trader may import this package (import-linter contract "AI views never feed
trading", ADR-009).

- `scoring`: pure grading and trading-day arithmetic.
- `service.record_view`: the tool-server entry point (see its module docstring).
- `scorer.score_views`: the worker's daily grading and rebuild.
- `report`: observation lists, hit-rates, AI spend.
"""
