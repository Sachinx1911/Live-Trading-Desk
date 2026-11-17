"""arq worker settings. Jobs live in worker.jobs; each has a DB row as source of truth."""

from __future__ import annotations

from typing import Any

from arq.connections import RedisSettings
from arq.cron import cron

from core.logging import configure_logging, get_logger
from core.settings import get_settings
from worker.jobs.system import heartbeat

log = get_logger(__name__)


async def startup(ctx: dict[str, Any]) -> None:
    s = get_settings()
    configure_logging(s.log_level, s.log_json)
    ctx["settings"] = s
    log.info("worker.started", env=s.app_env)


async def shutdown(ctx: dict[str, Any]) -> None:
    log.info("worker.stopped")


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(get_settings().redis_url)


class WorkerSettings:
    functions = [heartbeat]
    cron_jobs = [cron(heartbeat, minute=set(range(0, 60, 5)), run_at_startup=True)]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = _redis_settings()
    max_jobs = 10
    job_timeout = 60 * 60
