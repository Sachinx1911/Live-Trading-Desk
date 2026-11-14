# ADR-004: TimescaleDB from Phase 1

**Status:** Accepted (deviation from roadmap Phase 8) · **Date:** 2026-11-14

## Context
The prompt schedules TimescaleDB for Phase 8. Candles and quotes are written from Phase 2.
Migrating a year of time-series data into hypertables later is avoidable work.

## Decision
The Postgres image used everywhere is `timescale/timescaledb-ha`. `historical_candles`,
`market_quotes`, `option_chain_snapshots` and `tick_events` are hypertables from their
first migration, with compression and retention policies declared up front.

## Consequences
- No migration later; Phase 8 becomes "add Parquet cold archive and own ingestion", not
  "move the database".
- Alembic migrations include Timescale-specific SQL (`create_hypertable`, policies).
