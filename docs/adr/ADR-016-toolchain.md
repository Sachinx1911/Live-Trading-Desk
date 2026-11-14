# ADR-016: Toolchain

**Status:** Accepted · **Date:** 2026-11-14

## Decision
- Python 3.12+ via `uv` (lockfile committed). Ruff for lint/format, mypy strict on `packages/`.
- Node 24 via `pnpm`. Next.js (current stable, App Router), TypeScript strict, Tailwind,
  shadcn/ui, TanStack Query, Zustand, Lightweight Charts, `openapi-typescript` for generated types.
- Postgres 16 + TimescaleDB, Redis 7, MinIO, all via Docker Compose.
- pytest + hypothesis + pytest-asyncio; Playwright for a small set of web smoke tests.
- GitHub Actions: lint, type-check, tests, migration check, web build.
- Secrets: `.env` locally, documented in `.env.example`; broker credentials encrypted at
  rest with a key from `.env` (`SECRETS_KEY`).
