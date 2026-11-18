"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from api.middleware import RequestLogMiddleware
from api.routers import (
    auth,
    backtests,
    brokers,
    dsl,
    events,
    health,
    imports,
    market,
    nl_builder,
    paper,
    providers,
    regime,
    replay,
    risk,
    scanner,
    strategies,
)
from api.state import AppState
from api.ws import market as ws_market
from api.ws import replay as ws_replay
from core.logging import configure_logging, get_logger
from core.settings import get_settings

API_PREFIX = "/api/v1"
VERSION = "0.1.0"

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    state = AppState.create(settings)
    app.state.app = state
    await state.startup()
    if settings.dev_auto_login_enabled:
        log.warning("auth.dev_auto_login_enabled", email=settings.dev_auto_login_email)
    log.info("api.started", env=settings.app_env, provider=settings.default_market_data_provider)
    try:
        yield
    finally:
        await state.shutdown()
        log.info("api.stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Trading Platform API",
        version=VERSION,
        default_response_class=ORJSONResponse,
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestLogMiddleware)
    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(auth.router, prefix=API_PREFIX)
    app.include_router(providers.router, prefix=API_PREFIX)
    app.include_router(brokers.router, prefix=API_PREFIX)
    app.include_router(market.router, prefix=API_PREFIX)
    app.include_router(regime.router, prefix=API_PREFIX)
    app.include_router(scanner.router, prefix=API_PREFIX)
    app.include_router(nl_builder.router, prefix=API_PREFIX)
    app.include_router(dsl.router, prefix=API_PREFIX)  # before /strategies/{id}
    app.include_router(strategies.router, prefix=API_PREFIX)
    app.include_router(events.router, prefix=API_PREFIX)
    app.include_router(paper.router, prefix=API_PREFIX)
    app.include_router(risk.router, prefix=API_PREFIX)
    app.include_router(backtests.router, prefix=API_PREFIX)
    app.include_router(replay.router, prefix=API_PREFIX)
    app.include_router(imports.router, prefix=API_PREFIX)
    app.include_router(ws_replay.router)
    app.include_router(ws_market.router)
    return app


app = create_app()
