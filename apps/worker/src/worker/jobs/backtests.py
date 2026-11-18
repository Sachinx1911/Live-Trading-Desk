"""Backtest, optimisation and walk-forward jobs (Phase 4).

The `backtest` package does the work; this module owns the job rows, progress reporting,
cancellation and persistence. `backtest` is imported lazily so the worker boots even if the
package is being developed in parallel.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_session_factory
from core.db.models import (
    BacktestJob,
    BacktestResult,
    BacktestTrade,
    OptimizationJob,
    OptimizationResult,
    StrategyVersion,
)
from core.db.models._enums import JobStatus, OptimizationKind
from core.logging import get_logger
from core.models import Candle, Timeframe
from core.time import utcnow
from market_data.repo.candles import fetch_candles
from market_data.repo.instruments import get_instrument

log = get_logger(__name__)

MAX_CURVE_POINTS = 2000


class JobCancelled(Exception):  # noqa: N818 - domain signal, not an error
    pass


# ---------------------------------------------------------------------------- progress


def progress_key(kind: str, job_id: int) -> str:
    return f"{kind}:{job_id}:progress"


def cancel_key(kind: str, job_id: int) -> str:
    return f"{kind}:{job_id}:cancel"


class ProgressReporter:
    """Writes `{kind}:{id}:progress` to Redis and raises JobCancelled when the cancel flag is
    set. Used synchronously from inside the (CPU-bound) backtest loop via `sync()`."""

    def __init__(self, redis: Redis, kind: str, job_id: int, *, step_pct: float = 5.0) -> None:
        self.redis = redis
        self.kind = kind
        self.job_id = job_id
        self.step_pct = step_pct
        self.last_pct = -1.0
        self.last_db_pct = -1.0
        self._loop = asyncio.get_event_loop()
        self.cancelled = False

    async def report(self, pct: float, message: str = "") -> None:
        pct = max(0.0, min(100.0, float(pct)))
        if await self.redis.exists(cancel_key(self.kind, self.job_id)):
            self.cancelled = True
            raise JobCancelled(f"{self.kind} {self.job_id} cancelled")
        first = self.last_pct < 0
        if not first and pct - self.last_pct < self.step_pct and pct < 100.0:
            return
        self.last_pct = pct
        payload = f'{{"pct": {pct:.1f}, "message": "{message}", "at": "{utcnow().isoformat()}"}}'
        await self.redis.set(progress_key(self.kind, self.job_id), payload, ex=3600)

    def sync(self) -> Callable[[float, str], None]:
        """Callback for synchronous code: schedules the async report on the loop."""

        def _cb(pct: float, message: str = "") -> None:
            if self.cancelled:
                raise JobCancelled(f"{self.kind} {self.job_id} cancelled")
            fut = asyncio.run_coroutine_threadsafe(self.report(pct, message), self._loop)
            # When called from the loop thread itself, run_coroutine_threadsafe would
            # deadlock; fall back to a task in that case.
            try:
                running = asyncio.get_running_loop()
            except RuntimeError:
                running = None
            if running is self._loop:
                fut.cancel()
                self._loop.create_task(self.report(pct, message))

        return _cb


def _downsample(points: list[Any], limit: int = MAX_CURVE_POINTS) -> list[Any]:
    if len(points) <= limit:
        return points
    step = len(points) / limit
    out = [points[int(i * step)] for i in range(limit)]
    if out[-1] is not points[-1]:
        out.append(points[-1])
    return out


def _json(v: Any) -> Any:
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, dict):
        return {str(k): _json(x) for k, x in v.items()}
    if isinstance(v, list | tuple):
        return [_json(x) for x in v]
    return v


# ---------------------------------------------------------------------------- data


async def _load_candles(
    db: AsyncSession, instrument_id: int, timeframe: Timeframe, start: datetime, end: datetime
) -> tuple[list[Candle], Timeframe]:
    """Prefer 1-minute bars (the engine resamples); fall back to the job timeframe."""
    ones = await fetch_candles(db, instrument_id, Timeframe.M1, start, end)
    if ones:
        return ones, Timeframe.M1
    return await fetch_candles(db, instrument_id, timeframe, start, end), timeframe


async def _version_dsl(db: AsyncSession, version_id: int) -> dict[str, Any]:
    v = await db.get(StrategyVersion, version_id)
    if v is None:
        raise ValueError(f"strategy version {version_id} not found")
    return dict(v.dsl)


def _build_config(
    job: BacktestJob | OptimizationJob,
    dsl: dict[str, Any],
    instrument: Any,
    candles_tf: Timeframe,
    **overrides: Any,
) -> Any:
    from backtest.config import BacktestConfig, SlippageConfig
    from risk.limits import RiskLimits

    cfg = dict(job.config or {})
    cfg.update(overrides)
    timeframe = cfg.pop("timeframe", None) or getattr(job, "timeframe", None)
    tf_val = getattr(timeframe, "value", timeframe)
    # Job rows carry the exact UTC span; the API config keeps the user's IST dates.
    start = overrides.get("start") or getattr(job, "start_at", None)
    end = overrides.get("end") or getattr(job, "end_at", None)
    sl = cfg.pop("slippage", None) or {}
    slippage = SlippageConfig(
        model=sl.get("model", "spread_aware"),
        bps=float(sl.get("bps", 2.0)),
        size_impact_per_lot=float(sl.get("size_impact", sl.get("size_impact_per_lot", 0.5))),
    )
    rl = cfg.pop("risk_limits", None)
    return BacktestConfig(
        strategy_version_id=job.strategy_version_id,
        dsl=dsl,
        instrument=instrument,
        timeframe=Timeframe(tf_val) if tf_val else candles_tf,
        start=start,
        end=end,
        initial_capital=Decimal(str(cfg.pop("initial_capital", 100000))),
        risk_limits=RiskLimits.model_validate(rl) if rl else RiskLimits(),
        slippage=slippage,
        seed=int(cfg.pop("seed", getattr(job, "seed", 42))),
        fill_mode=cfg.pop("fill_mode", "next_bar_open"),
        param_overrides=cfg.pop("param_overrides", {}) or {},
        label=cfg.pop("label", None) or getattr(job, "label", None) or "",
    )


def _objective(name: str) -> Any:
    allowed = {"sharpe", "net_pnl", "calmar", "expectancy", "profit_factor", "sortino"}
    return name if name in allowed else "sharpe"


# ---------------------------------------------------------------------------- backtest


async def _persist_result(db: AsyncSession, job: BacktestJob, result: Any) -> BacktestResult:
    from backtest.report import render_report

    try:
        report_md = render_report(result)
    except Exception as exc:
        report_md = f"report unavailable: {exc}"
    row = BacktestResult(
        job_id=job.id,
        metrics=_json(result.metrics.as_dict()),
        equity_curve=_json(_downsample(list(result.equity_curve))),
        drawdown_curve=_json(_downsample(list(result.drawdown_curve))),
        monthly_table=_json(list(result.monthly_table)),
        assumptions=_json(dict(result.assumptions)),
        data_hash=getattr(result, "data_hash", None),
        engine_stats=_json(dict(getattr(result, "stats", {}) or {})),
        warnings=list(getattr(result, "warnings", []) or []),
        elapsed_s=Decimal(str(round(float(getattr(result, "elapsed_s", 0) or 0), 3))),
        report_md=report_md,
    )
    db.add(row)
    await db.flush()
    trades = [
        BacktestTrade(
            result_id=row.id,
            instrument_id=t.instrument_id,
            side=t.side,
            quantity=t.quantity,
            entry_at=t.entry_at,
            entry_price=t.entry_price,
            exit_at=t.exit_at,
            exit_price=t.exit_price,
            gross_pnl=t.gross_pnl,
            costs=t.costs,
            net_pnl=t.net_pnl,
            entry_reason=getattr(t, "entry_reason", None),
            exit_reason=getattr(t, "exit_reason", None),
            bars_held=getattr(t, "bars_held", None),
            mae=getattr(t, "mae", None),
            mfe=getattr(t, "mfe", None),
        )
        for t in result.trades
    ]
    if trades:
        db.add_all(trades)
    return row


async def _set_status(
    db: AsyncSession,
    job: BacktestJob | OptimizationJob,
    status: JobStatus,
    *,
    error: str | None = None,
    pct: float | None = None,
) -> None:
    job.status = status
    if error is not None:
        job.error = error[:4000]
    if pct is not None:
        job.progress_pct = Decimal(str(round(pct, 2)))
    now = utcnow()
    if status == JobStatus.RUNNING:
        job.started_at = now
    elif status in (JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED):
        job.finished_at = now
    await db.commit()


async def run_backtest_job(ctx: dict[str, Any], job_id: int) -> dict[str, Any]:
    redis: Redis = ctx["redis"]
    reporter = ProgressReporter(redis, "backtest", job_id)
    async with get_session_factory()() as db:
        job = await db.get(BacktestJob, job_id)
        if job is None:
            return {"error": f"backtest job {job_id} not found"}
        if job.status not in (JobStatus.QUEUED, JobStatus.FAILED):
            return {"skipped": job.status.value}
        await _set_status(db, job, JobStatus.RUNNING, pct=0)
        try:
            from backtest.runner import run_backtest

            dsl = await _version_dsl(db, job.strategy_version_id)
            instrument = await get_instrument(db, job.instrument_id)
            if instrument is None:
                raise ValueError(f"instrument {job.instrument_id} not found")
            candles, ctf = await _load_candles(
                db, job.instrument_id, job.timeframe, job.start_at, job.end_at
            )
            if not candles:
                raise ValueError("no candles stored for the requested range; backfill first")
            config = _build_config(job, dsl, instrument, ctf, timeframe=job.timeframe.value)
            job.config_hash = config.config_hash()
            await reporter.report(1, f"{len(candles)} bars loaded")
            running_job = job
            last_db = 0.0

            async def on_progress(pct: float, message: str = "") -> None:
                nonlocal last_db
                await reporter.report(pct, message)
                if pct - last_db >= 5:
                    last_db = pct
                    running_job.progress_pct = Decimal(str(round(pct, 2)))
                    await db.commit()

            cb = reporter.sync()
            result = await asyncio.to_thread(
                run_backtest, config, candles, progress=lambda pct: cb(pct, "")
            )
            await on_progress(99, "persisting")
            await _persist_result(db, job, result)
            await _set_status(db, job, JobStatus.SUCCEEDED, pct=100)
            await reporter.report(100, "done")
            log.info(
                "backtest.done",
                job=job_id,
                trades=len(result.trades),
                elapsed_s=getattr(result, "elapsed_s", None),
            )
            return {
                "job_id": job_id,
                "trades": len(result.trades),
                "metrics": _json(result.metrics.as_dict()),
            }
        except JobCancelled:
            await _set_status(db, job, JobStatus.CANCELLED, error="cancelled by user")
            return {"job_id": job_id, "status": "cancelled"}
        except Exception as exc:
            log.error("backtest.failed", job=job_id, error=str(exc))
            await db.rollback()
            job = await db.get(BacktestJob, job_id)
            if job is not None:
                await _set_status(db, job, JobStatus.FAILED, error=f"{type(exc).__name__}: {exc}")
            return {"job_id": job_id, "status": "failed", "error": str(exc)}


# ---------------------------------------------------------------------------- optimisation


async def _store_rows(
    db: AsyncSession,
    job: OptimizationJob,
    rows: list[Any],
    *,
    is_oos: bool,
    window: dict[str, Any] | None = None,
    offset: int = 0,
) -> int:
    n = 0
    for i, r in enumerate(rows):
        params = r.get("params", {}) if isinstance(r, dict) else getattr(r, "params", {})
        metrics = r.get("metrics", {}) if isinstance(r, dict) else getattr(r, "metrics", {})
        rank = (
            r.get("rank", offset + i + 1)
            if isinstance(r, dict)
            else getattr(r, "rank", offset + i + 1)
        )
        db.add(
            OptimizationResult(
                job_id=job.id,
                rank=int(rank),
                params=_json(dict(params)),
                metrics=_json(dict(metrics)),
                window=_json(window)
                if window
                else (_json(r.get("window")) if isinstance(r, dict) and r.get("window") else None),
                is_oos=bool(r.get("is_oos", is_oos)) if isinstance(r, dict) else is_oos,
            )
        )
        n += 1
    return n


async def run_optimization_job(ctx: dict[str, Any], job_id: int) -> dict[str, Any]:
    redis: Redis = ctx["redis"]
    reporter = ProgressReporter(redis, "optimization", job_id)
    async with get_session_factory()() as db:
        job = await db.get(OptimizationJob, job_id)
        if job is None:
            return {"error": f"optimization job {job_id} not found"}
        if job.kind == OptimizationKind.WALK_FORWARD:
            return await _walk_forward(ctx, db, job, reporter)
        if job.status not in (JobStatus.QUEUED, JobStatus.FAILED):
            return {"skipped": job.status.value}
        await _set_status(db, job, JobStatus.RUNNING, pct=0)
        try:
            from backtest.optimize import optimize

            dsl = await _version_dsl(db, job.strategy_version_id)
            instrument = await get_instrument(db, job.instrument_id)
            if instrument is None:
                raise ValueError(f"instrument {job.instrument_id} not found")
            cfg = dict(job.config or {})
            tf = Timeframe(cfg.get("timeframe", "5m"))
            start = (
                datetime.fromisoformat(cfg["start"])
                if cfg.get("start")
                else utcnow() - timedelta(days=365)
            )
            end = datetime.fromisoformat(cfg["end"]) if cfg.get("end") else utcnow()
            candles, ctf = await _load_candles(db, job.instrument_id, tf, start, end)
            if not candles:
                raise ValueError("no candles stored for the requested range; backfill first")
            base = _build_config(
                job, dsl, instrument, ctf, timeframe=tf.value, start=start, end=end
            )
            await reporter.report(1, f"{len(candles)} bars loaded")
            cb = reporter.sync()
            out = await asyncio.to_thread(
                optimize,
                base,
                candles,
                job.param_space,
                objective=_objective(job.objective),
                method="random" if job.kind.value == "random" else "grid",
                max_runs=int(cfg.get("max_runs", 200)),
                progress=lambda pct: cb(pct, ""),
            )
            rows = [
                {"rank": r.rank, "params": r.params, "metrics": r.metrics.as_dict()}
                for r in out.rows
            ]
            n = await _store_rows(db, job, rows, is_oos=False)
            job.config = {
                **cfg,
                "sensitivity": _json(out.sensitivity),
                "plateau_score": out.plateau_score,
                "flags": _json(out.overfit_flags),
                "runs": out.runs,
            }
            await _set_status(db, job, JobStatus.SUCCEEDED, pct=100)
            await reporter.report(100, "done")
            log.info("optimization.done", job=job_id, rows=n)
            return {"job_id": job_id, "rows": n, "flags": _json(getattr(out, "flags", None))}
        except JobCancelled:
            await _set_status(db, job, JobStatus.CANCELLED, error="cancelled by user")
            return {"job_id": job_id, "status": "cancelled"}
        except Exception as exc:
            log.error("optimization.failed", job=job_id, error=str(exc))
            await db.rollback()
            job = await db.get(OptimizationJob, job_id)
            if job is not None:
                await _set_status(db, job, JobStatus.FAILED, error=f"{type(exc).__name__}: {exc}")
            return {"job_id": job_id, "status": "failed", "error": str(exc)}


async def _walk_forward(
    ctx: dict[str, Any], db: AsyncSession, job: OptimizationJob, reporter: ProgressReporter
) -> dict[str, Any]:
    if job.status not in (JobStatus.QUEUED, JobStatus.FAILED):
        return {"skipped": job.status.value}
    await _set_status(db, job, JobStatus.RUNNING, pct=0)
    try:
        from backtest.walk_forward import walk_forward

        dsl = await _version_dsl(db, job.strategy_version_id)
        instrument = await get_instrument(db, job.instrument_id)
        if instrument is None:
            raise ValueError(f"instrument {job.instrument_id} not found")
        cfg = dict(job.config or {})
        tf = Timeframe(cfg.get("timeframe", "5m"))
        start = (
            datetime.fromisoformat(cfg["start"])
            if cfg.get("start")
            else utcnow() - timedelta(days=730)
        )
        end = datetime.fromisoformat(cfg["end"]) if cfg.get("end") else utcnow()
        candles, ctf = await _load_candles(db, job.instrument_id, tf, start, end)
        if not candles:
            raise ValueError("no candles stored for the requested range; backfill first")
        base = _build_config(job, dsl, instrument, ctf, timeframe=tf.value, start=start, end=end)
        windows = job.windows or {"train_days": 180, "test_days": 60, "step_days": 60}
        await reporter.report(1, f"{len(candles)} bars loaded")
        cb = reporter.sync()
        out = await asyncio.to_thread(
            walk_forward,
            base,
            candles,
            job.param_space,
            train_days=int(windows["train_days"]),
            test_days=int(windows["test_days"]),
            step_days=int(windows.get("step_days") or windows["test_days"]),
            objective=_objective(job.objective),
            max_runs_per_window=int(cfg.get("max_runs", 100)),
            progress=lambda pct: cb(pct, ""),
        )
        n = 0
        for idx, w in enumerate(out.windows):
            win = w.window
            wd = {
                "index": idx,
                "train_start": getattr(win, "train_start", None),
                "train_end": getattr(win, "train_end", None),
                "test_start": getattr(win, "test_start", None),
                "test_end": getattr(win, "test_end", None),
                "params": w.params,
                "is_metrics": w.in_sample.as_dict(),
                "oos_metrics": w.out_of_sample.as_dict(),
            }
            n += await _store_rows(
                db,
                job,
                [
                    {
                        "params": wd.get("params", {}),
                        "metrics": wd.get("is_metrics", {}),
                        "rank": n + 1,
                    }
                ],
                is_oos=False,
                window=_json(
                    {
                        k: v
                        for k, v in wd.items()
                        if k in ("train_start", "train_end", "test_start", "test_end", "index")
                    }
                ),
            )
            n += await _store_rows(
                db,
                job,
                [
                    {
                        "params": wd.get("params", {}),
                        "metrics": wd.get("oos_metrics", {}),
                        "rank": n + 1,
                    }
                ],
                is_oos=True,
                window=_json(
                    {
                        k: v
                        for k, v in wd.items()
                        if k in ("train_start", "train_end", "test_start", "test_end", "index")
                    }
                ),
            )
        job.config = {
            **cfg,
            "windows": windows,
            "oos_metrics": _json(out.oos_metrics.as_dict()),
            "oos_equity": _json(_downsample(list(out.oos_equity))),
            "is_oos_ratio": out.is_oos_ratio,
            "flags": _json(out.flags),
        }
        await _set_status(db, job, JobStatus.SUCCEEDED, pct=100)
        await reporter.report(100, "done")
        log.info("walk_forward.done", job=job.id, windows=len(out.windows))
        return {
            "job_id": job.id,
            "windows": len(out.windows),
            "oos_metrics": job.config["oos_metrics"],
        }
    except JobCancelled:
        await _set_status(db, job, JobStatus.CANCELLED, error="cancelled by user")
        return {"job_id": job.id, "status": "cancelled"}
    except Exception as exc:
        log.error("walk_forward.failed", job=job.id, error=str(exc))
        await db.rollback()
        fresh = await db.get(OptimizationJob, job.id)
        if fresh is not None:
            await _set_status(db, fresh, JobStatus.FAILED, error=f"{type(exc).__name__}: {exc}")
        return {"job_id": job.id, "status": "failed", "error": str(exc)}


async def run_walk_forward_job(ctx: dict[str, Any], job_id: int) -> dict[str, Any]:
    """Alias so callers can enqueue walk-forward explicitly; the kind column decides anyway."""
    return await run_optimization_job(ctx, job_id)
