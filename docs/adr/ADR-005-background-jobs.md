# ADR-005: arq on Redis for background jobs

**Status:** Accepted · **Date:** 2026-11-14

## Context
Backtests, optimisation sweeps, AI research, imports and nightly data jobs take seconds to
hours. They cannot run inside an HTTP request.

## Decision
`apps/worker` runs arq workers. Jobs are idempotent, carry a `job_id` stored in the DB
(`backtest_jobs`, `ai_research_jobs`, `data_import_jobs`) and publish progress to Redis so
the UI can stream it over WebSocket. Scheduled jobs (instrument master refresh, EOD
compaction, nightly research) use arq's cron support.

Celery was rejected as heavier than needed; it remains a drop-in option if arq limits are hit.

## Consequences
- Redis is a hard dependency from Phase 1.
- Every job type has a DB row that is the source of truth for status; Redis is transport.
