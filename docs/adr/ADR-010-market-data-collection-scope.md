# ADR-010: Market data collection scope for Phases 2–7

**Status:** Accepted · **Date:** 2026-11-14

## Context
Tick and 30-level depth capture is possible from Upstox/Dhan but is not needed by any
Phase 2–7 feature. 1-minute candles and options-chain snapshots *are* needed and cannot
be obtained retroactively from brokers.

## Decision
The collector (`apps/collector`, extracted from the worker in Phase 2) always stores:
- 1-minute candles built from the live feed for all tracked instruments.
- Options-chain snapshots every 3 minutes (`COLLECT_CHAIN_INTERVAL_S`, was 5 until 2026-11-21; the exchange refreshes OI about every 3 minutes) for tracked expiries (OI, ΔOI, IV, LTP, bid/ask).
- India VIX at 1-minute resolution.
- The bid/ask at the moment of every paper fill.

Raw tick and depth archiving to Parquet is implemented behind `COLLECT_RAW_TICKS=false`.
It can be enabled per instrument group without code changes.

## Consequences
- Storage stays in the low-GB range per year until raw ticks are switched on.
- Order-flow research is possible later only from the date the flag was enabled.
