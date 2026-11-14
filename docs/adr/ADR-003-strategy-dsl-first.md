# ADR-003: Strategy DSL is the only executable strategy form; no Python editor in v1

**Status:** Accepted (deviation from master prompt Module 7) · **Date:** 2026-11-14

## Context
The prompt asks for a Python Strategy Editor and, elsewhere, forbids executing arbitrary
code. User-written Python is arbitrary code. Sandboxing Python safely (no network, CPU
and memory limits, restricted imports, no filesystem) is a project in itself and still
leaks via timing and resource exhaustion.

## Decision
Strategies exist only as DSL documents validated by Pydantic models and a published JSON
Schema (`packages/strategy/dsl`). Natural language, the visual builder and AI research all
produce the same DSL. The Python editor is removed from v1 scope. If it returns later it
will run in an isolated container with a hard time budget and may only *emit* DSL.

## Consequences
- The DSL must be expressive enough: indicators with parameters, comparisons, crossovers,
  AND/OR trees, time-of-day filters, regime filters, stop/target in ATR/points/percent,
  position sizing rules, session rules (intraday square-off).
- Indicator library is fixed and versioned; adding an indicator is a code change with tests.
