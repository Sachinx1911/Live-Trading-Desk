# ADR-006: UTC in storage, exchange timezone at the edges

**Status:** Accepted · **Date:** 2026-11-14

## Context
NSE is IST (UTC+5:30, no DST). Future markets have other zones and DST. Mixing naive and
aware timestamps is the most common source of off-by-one-candle bugs.

## Decision
- All DB columns are `timestamptz`; all Python datetimes are aware UTC.
- Each `exchanges` row carries an IANA timezone and session rules.
- Candle `ts` is the **open** time of the bar in UTC. Daily bars use the session open.
- The provider's own timestamp is stored separately as `provider_ts` for latency and
  comparison analysis.
- Frontend converts to the selected market's timezone for display only.

## Consequences
- Trading calendars and session logic live in `packages/core/calendar`, tested per exchange.
