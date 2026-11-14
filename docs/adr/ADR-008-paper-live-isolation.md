# ADR-008: Paper and live are isolated

**Status:** Accepted · **Date:** 2026-11-14

## Decision
Separate tables (`paper_accounts/paper_orders/paper_positions/paper_trades` vs
`live_accounts/live_orders/live_positions/live_trades`), separate service classes, separate
API routes (`/paper/...` vs `/live/...`). The strategy engine emits signals; a `TradingMode`
binding decides whether they reach the simulator or the live gateway. A strategy
activation is bound to exactly one mode.

## Consequences
- Some duplication in schema, deliberately. A shared `trades` view can exist for analytics,
  read-only.
- The UI uses distinct colour tags for paper and live everywhere.
