# ADR-007: Single live-order gateway behind five gates

**Status:** Accepted · **Date:** 2026-11-14

## Decision
`packages/execution/live/gateway.py::submit_live_order` is the only code path to a broker's
order API. It refuses unless all pass, in order:

1. Strategy version status is `approved_live` and the activation record is signed by the user.
2. Broker session is valid (token not expired, account matches).
3. Risk engine returns `ALLOW` (position size, per-trade risk, exposure, correlation,
   event block, session window, freeze quantity).
4. Daily and weekly loss limits for the live account are not breached.
5. Kill switch (global, account, strategy) is off.

Every call, allowed or refused, writes an `order_events` row and an `audit_logs` row. An
idempotency key (strategy_version_id + signal_id) prevents duplicate submission.

## Consequences
- Tests assert that no other module imports the broker order client.
- The kill switch is a Redis flag plus a DB record; the gateway checks Redis on every call.
