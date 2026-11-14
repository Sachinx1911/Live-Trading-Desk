# ADR-015: Monorepo layout

**Status:** Accepted · **Date:** 2026-11-14

## Decision
See `docs/architecture/02-folder-structure.md`. Summary: `apps/` (api, worker, collector,
web), `packages/` (core, market_data, providers, strategy, execution, backtest, ai,
portfolio, risk), `infra/` (docker, migrations, nginx, ci), `docs/`.

One `pyproject.toml` at the root with uv workspaces; one `package.json` workspace for web.

## Consequences
- A single `docker compose up` and a single CI pipeline.
- Package import boundaries are enforced in CI.
