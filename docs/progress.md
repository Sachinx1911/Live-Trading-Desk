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
- [ ] Plan reviewed by product owner

## Phase 1 · Foundation

- [ ] Repo scaffold: uv workspace, pnpm workspace, docker compose (Timescale, Redis, MinIO)
- [ ] `packages/core`: canonical models, settings, db session, time/calendar utils, logging
- [ ] Alembic + first migrations (identity, reference data, instruments skeleton, strategies skeleton, audit)
- [ ] FastAPI skeleton: health, auth (login/refresh/me), audit middleware
- [ ] `MarketDataProvider` / `BrokerAdapter` interfaces + fake provider (is_demo)
- [ ] Next.js shell: design tokens, layout, sidebar, auth pages, dashboard with real provider status and explicit Disconnected/Demo states
- [ ] CI: ruff, mypy, pytest, alembic check, web build
- [ ] `.env.example` documented
