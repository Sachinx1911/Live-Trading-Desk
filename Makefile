.PHONY: up down sync lint type test migrate api worker web gen-api check tool-server

up:            ## start local infrastructure
	docker compose up -d
down:
	docker compose down
sync:          ## install python workspace
	uv sync --all-packages
lint:
	uv run ruff check . && uv run ruff format --check .
fmt:
	uv run ruff format . && uv run ruff check --fix .
type:
	uv run mypy packages apps/api/src apps/worker/src
test:
	uv run pytest
migrate:
	uv run alembic -c infra/migrations/alembic.ini upgrade head
api:
	uv run uvicorn api.main:app --reload --port 8000
worker:
	uv run arq worker.main.WorkerSettings
collector:
	uv run python -m collector.main
trader:
	uv run python -m trader.main
tool-server:   ## jarvis tool server: HTTP /tools + MCP /mcp on TOOL_SERVER_HOST:PORT (127.0.0.1:8100)
	uv run python -m tool_server.main
web:
	pnpm --dir apps/web dev
gen-api:       ## regenerate TypeScript API types from the running API
	pnpm --dir apps/web gen:api
check: lint type test
seed-owner:    ## create/reset the local owner user from DEV_OWNER_* in .env
	set -a; . ./.env; set +a; OWNER_PASSWORD="$$DEV_OWNER_PASSWORD" uv run python infra/scripts/create_owner_user.py "$$DEV_OWNER_EMAIL"
