# ADR-013: News and sentiment deferred

**Status:** Accepted (deviation: Module 3 moves after Phase 6) · **Date:** 2026-11-14

## Context
No licensed, timestamped, India-focused news source has been chosen. Free scraping is
legally and technically fragile and adds noise to intraday systems.

## Decision
Module 3 is deferred until a source is selected and budgeted. Until then an `events`
table (RBI, Fed, budget, results, expiry) feeds the risk engine's event block rule, which
covers the main protective use of news.

## Consequences
- The `NewsProvider` interface is defined in `packages/ai/news` so the module can be added without core changes.
