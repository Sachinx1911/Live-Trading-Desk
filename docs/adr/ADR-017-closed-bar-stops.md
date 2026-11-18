# ADR-017: Stops and targets are evaluated on closed bars in every mode

**Status:** Accepted · **Date:** 2026-11-18

## Context
The strategy engine checks stop-loss and target levels when a bar closes (`monitor_levels`).
The execution simulator can also hold resting stop orders that trigger intra-bar on ticks.
Mixing the two would make paper trading (ticks available) and backtesting (bars only) fill
at different prices for the same strategy, breaking ADR-002.

## Decision
Phase 3–4 use closed-bar stop/target evaluation in paper trading, replay and backtesting
alike; the engine emits `stop`/`target` signals and the simulator fills them as market
orders on the next event. Intra-bar stop semantics will be introduced only when the
backtester can model them from the same data (1-minute bars under a coarser strategy
timeframe), and then switched on for both modes in the same release.

## Consequences
- Fills past the stop level within a bar are a known, documented source of slippage;
  strategies on 15m/1h bars should size for it (ATR-based stops).
- Backtest and paper results remain comparable, which is the property we value more.
