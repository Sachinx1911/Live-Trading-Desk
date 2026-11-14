# ADR-011: Corporate actions, trading calendars and cost schedules are first-class tables

**Status:** Accepted (addition to master prompt §9) · **Date:** 2026-11-14

## Context
Equity backtests from 2010 are wrong without split/bonus/dividend adjustments. Indian
transaction costs (STT, exchange charges, stamp duty, SEBI fee, GST) have changed several
times; backtests must apply the rate in force on the trade date. Holidays and special
sessions (Muhurat, budget Saturday) must be known per exchange.

## Decision
Add `corporate_actions` (instrument, ex_date, type, ratio/amount, source),
`trading_calendars` (exchange, date, session type, open/close), and `cost_schedules`
(exchange, segment, product, charge type, rate, effective_from, effective_to, source).
Adjusted prices are a derived view, never stored over raw.

## Consequences
- Instrument master import also imports lot-size and tick-size history into `instrument_history`.
- The cost model in the simulator takes a trade date and looks up the schedule.
