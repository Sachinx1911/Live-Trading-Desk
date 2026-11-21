"""arq worker settings. Jobs live in worker.jobs; each has a DB row as source of truth."""

from __future__ import annotations

from typing import Any

from arq.connections import RedisSettings
from arq.cron import cron

from core.logging import configure_logging, get_logger
from core.settings import get_settings
from worker.jobs.alerts import evaluate_alerts
from worker.jobs.backtests import run_backtest_job, run_optimization_job, run_walk_forward_job
from worker.jobs.breadth import compute_market_breadth, rebuild_market_breadth
from worker.jobs.brokers import check_broker_sessions
from worker.jobs.daily_refresh import refresh_daily_candles
from worker.jobs.market_data import backfill_instrument, eod_gap_report, sync_instruments
from worker.jobs.news import ingest_news
from worker.jobs.nse_reference import import_nse_reference
from worker.jobs.protocols import run_protocol
from worker.jobs.regime import compute_regime_daily, compute_regime_intraday
from worker.jobs.reports import generate_evening_brief
from worker.jobs.scanner import compute_scan_snapshot
from worker.jobs.strike_series import rebuild_strike_series_job
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
        run_backtest_job,
        run_optimization_job,
        run_walk_forward_job,
        compute_regime_daily,
        compute_regime_intraday,
        compute_scan_snapshot,
        rebuild_strike_series_job,
        ingest_news,
        compute_market_breadth,
        rebuild_market_breadth,
        run_protocol,
        evaluate_alerts,
        refresh_daily_candles,
        generate_evening_brief,
    ]
    cron_jobs = [
        cron(heartbeat, minute=set(range(0, 60, 5)), run_at_startup=True),
        # 08:15 IST = 02:45 UTC, then every 30 min through the session (03:00-10:00 UTC)
        cron(check_broker_sessions, hour={2}, minute={45}),
        cron(check_broker_sessions, hour=set(range(3, 11)), minute={0, 30}),
        # Upstox instrument file refreshes ~06:00 IST (00:30 UTC)
        cron(sync_instruments, hour={1}, minute={0}),
        # Official candles after the close (15:45 IST): daily for the universe, 1m repairs
        cron(refresh_daily_candles, hour={10}, minute={15}),
        # End of day: gap report 16:00 IST, NSE reference import 19:00 IST
        cron(eod_gap_report, hour={10}, minute={30}),
        cron(import_nse_reference, hour={13}, minute={30}),
        # Regime: 09:05 IST (previous close) and 16:10 IST; day type every 15 min in session
        cron(compute_regime_daily, hour={3}, minute={35}),
        cron(compute_regime_daily, hour={10}, minute={40}),
        cron(compute_regime_intraday, hour=set(range(4, 10)), minute={0, 15, 30, 45}),
        # scanner snapshot after the daily bars + regime land (16:20 IST)
        cron(compute_scan_snapshot, hour={10}, minute={50}),
        # market breadth after the scan snapshot (16:25 IST)
        cron(compute_market_breadth, hour={10}, minute={55}),
        # raw news every 30 min 07:00-22:30 IST = 01:30-17:00 UTC (job re-checks the window)
        cron(ingest_news, hour=set(range(1, 18)), minute={0, 30}),
        # evening brief 19:00 IST = 13:30 UTC (job skips non-trading days)
        cron(generate_evening_brief, hour={13}, minute={30}),
        # proactive alerts every minute 09:00-15:45 IST (job re-checks window + NSE calendar)
        cron(evaluate_alerts, hour=set(range(3, 11)), minute=set(range(60))),
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = _redis_settings()
    max_jobs = 10
    job_timeout = 60 * 60
