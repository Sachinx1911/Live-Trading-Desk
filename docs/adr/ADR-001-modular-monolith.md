# ADR-001: Modular monolith, not microservices

**Status:** Accepted · **Date:** 2026-11-14

## Context
The master prompt lists 30 modules and explicitly says not to introduce microservices
prematurely. The team is one developer plus AI assistance.

## Decision
One Python backend (`apps/api` + `apps/worker`) built from importable packages in
`packages/`. Package boundaries are enforced by import rules (a package may import only
`core` and its declared dependencies). Services are extracted only when a boundary has
proven stable and an operational reason exists (e.g. market-data collector must stay up
while the API restarts).

## Consequences
- Single deploy, single database, simple local dev.
- The market-data collector is the first candidate for extraction (Phase 2) because it
  must run independently of API deploys; it still shares the codebase.
- Import-linter (or an equivalent check) guards boundaries in CI.
