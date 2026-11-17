# Progress

Only items that are implemented **and tested** are ticked. "Designed" means the doc exists,
not that code exists.

## Phase 0 · Architecture (first task from the master prompt)

- [x] Master prompt preserved (`docs/MASTER_PROMPT.md`)
- [x] Architecture decision records ADR-001 … ADR-016
- [x] 01 System architecture
- [x] 02 Folder structure
- [x] 03 Database design
- [x] 04 API specification
- [x] 05 Strategy DSL
- [x] 06 UI page map
- [x] 07 Roadmap
- [x] 08 Risks and dependencies
- [x] Plan reviewed by product owner (2026-11-17)

## Phase 1 · Foundation

Verified 2026-11-17 on macOS with Docker Desktop: `docker compose up -d` (db on 5433, redis),
`alembic upgrade head`, `alembic check` (no drift), 32 pytest tests, ruff/mypy strict/import-linter
clean, API login → refresh rotation → providers, worker heartbeat in Redis, web login → dashboard
showing real provider status with explicit Disconnected/Demo states. Web: lint, typecheck, build pass.

- [x] Repo scaffold: uv workspace, pnpm app, docker compose (TimescaleDB, Redis; MinIO behind `--profile storage`)
- [x] `packages/core`: canonical models (instrument, candle, tick, quote, option chain, signal, order intent, fill, position), enums + order state table, settings, async db session, UTC time utils, NSE calendar, structlog, Fernet secret box, event bus
- [x] ORM models (30 tables) + Alembic migrations 0001–0005 (identity, reference seeds, instruments, strategies with immutability trigger, candles/quotes hypertables)
- [x] `MarketDataProvider` / `BrokerAdapter` interfaces, registry, deterministic fake provider (is_demo)
- [x] FastAPI: health, auth (login / refresh with rotation / logout / me), providers status, request logging, JWT + Argon2
- [x] arq worker skeleton with heartbeat cron
- [x] Next.js shell: design tokens, grouped sidebar (15 items), login, dashboard (provider status from API, no fabricated numbers), stub pages per phase
- [x] CI workflow (ruff, mypy, import-linter, alembic upgrade, pytest, web lint+build)
- [x] `.env.example` documented; `infra/scripts/create_owner_user.py` + `make seed-owner`
- [ ] Audit-log writes on state-changing endpoints (table exists; middleware hook lands with the first mutating endpoints in Phase 2)
- [ ] TOTP second factor (schema ready; UI/API in Phase 10 hardening)

## Phase 2 · Upstox integration + collector

- [ ] not started
