# ADR-002: One strategy engine and one execution simulator for backtest, replay and paper

**Status:** Accepted · **Date:** 2026-11-14

## Context
If backtesting, historical replay and paper trading each have their own strategy loop or
fill model, their results diverge and nobody can tell whether a strategy failed or the
code did.

## Decision
`packages/strategy/engine` evaluates DSL strategies against a stream of canonical market
events. `packages/execution/simulator` turns orders into fills using the same cost model,
slippage model and bid/ask logic everywhere. The three modes differ only in the event
source:

| Mode | Event source | Clock |
|------|--------------|-------|
| Backtest | Historical candles/ticks from DB/Parquet | Simulated, as fast as possible |
| Replay | Same as backtest | Simulated, user-controlled speed |
| Paper | Live WebSocket feed | Wall clock |

Live trading uses the same strategy engine but routes orders to the broker gateway
instead of the simulator.

## Consequences
- A strategy that works in backtest and fails in paper points to data/slippage
  assumptions, not code differences.
- The simulator must be deterministic given a seed, for reproducible backtests.
