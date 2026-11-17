"""arq worker settings. Jobs live in worker.jobs; each has a DB row as source of truth."""

from __future__ import annotations

from typing import Any

from arq.connections import RedisSettings
from arq.cron import cron

from core.logging import configure_logging, get_logger
from core.settings import get_settings
from worker.jobs.brokers import check_broker_sessions
from worker.jobs.market_data import backfill_instrument, eod_gap_report, sync_instruments
from worker.jobs.nse_reference import import_nse_reference
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
    functions = [
        heartbeat,
        check_broker_sessions,
        sync_instruments,
        backfill_instrument,
        eod_gap_report,
        import_nse_reference,
    ]
    cron_jobs = [
        cron(heartbeat, minute=set(range(0, 60, 5)), run_at_startup=True),
        # 08:15 IST = 02:45 UTC, then every 30 min through the session (03:00-10:00 UTC)
        cron(check_broker_sessions, hour={2}, minute={45}),
        cron(check_broker_sessions, hour=set(range(3, 11)), minute={0, 30}),
        # Upstox instrument file refreshes ~06:00 IST (00:30 UTC)
        cron(sync_instruments, hour={1}, minute={0}),
        # End of day: gap report 16:00 IST, NSE reference import 19:00 IST
        cron(eod_gap_report, hour={10}, minute={30}),
        cron(import_nse_reference, hour={13}, minute={30}),
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = _redis_settings()
    max_jobs = 10
    job_timeout = 60 * 60
