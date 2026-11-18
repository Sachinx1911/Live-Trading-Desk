"""Backtest, optimisation and walk-forward jobs. Jobs run in the worker (arq); this router
creates rows, enqueues, and reads results. Nothing here executes a strategy."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any

import orjson
from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from api.audit import audit
from api.deps import DB, State, User
from core.db.models import (
    BacktestJob,
    BacktestResult,
    BacktestTrade,
    OptimizationJob,
    OptimizationResult,
    StrategyVersion,
)
from core.db.models._enums import JobStatus, OptimizationKind
from core.models import Timeframe
from core.time import IST, ensure_utc, utcnow

router = APIRouter(prefix="/backtests", tags=["backtests"])


# ------------------------------------------------------------------ schemas
class SlippageIn(BaseModel):
    model: str = Field(default="spread_aware", pattern="^(fixed_bps|spread_aware)$")
    bps: float = 2.0
    size_impact: float = 0.5


class BacktestIn(BaseModel):
    strategy_version_id: int
    instrument_id: int
    start: date
    end: date
    timeframe: Timeframe | None = None
    initial_capital: Decimal = Field(default=Decimal("100000"), gt=0)
    seed: int = 42
    fill_mode: str = Field(default="next_bar_open", pattern="^(next_bar_open|bar_close)$")
    slippage: SlippageIn = SlippageIn()
    param_overrides: dict[str, Any] = {}
    risk_limits: dict[str, Any] | None = None
    label: str | None = None


class JobOut(BaseModel):
    id: int
    strategy_version_id: int
    instrument_id: int
    timeframe: str
    start_at: datetime
    end_at: datetime
    status: JobStatus
    progress_pct: float
    config: dict[str, Any]
    config_hash: str
    seed: int
    label: str | None
    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None
    has_result: bool = False


class ResultOut(BaseModel):
    job: JobOut
    metrics: dict[str, Any]
    equity_curve: list[Any]
    drawdown_curve: list[Any]
    monthly_table: list[Any] | dict[str, Any]
    assumptions: dict[str, Any]
    data_hash: str | None
    engine_stats: dict[str, Any]
    warnings: list[str]
    elapsed_s: float | None


class TradeOut(BaseModel):
    id: int
    instrument_id: int
    side: str
    quantity: int
    entry_at: datetime
    entry_price: Decimal
    exit_at: datetime
    exit_price: Decimal
    gross_pnl: Decimal
    costs: Decimal
    net_pnl: Decimal
    entry_reason: str | None
    exit_reason: str | None
    bars_held: int | None
    mae: Decimal | None
    mfe: Decimal | None


class OptimizationIn(BaseModel):
    strategy_version_id: int
    instrument_id: int
    start: date
    end: date
    kind: OptimizationKind = OptimizationKind.GRID
    param_space: dict[str, list[Any]] = Field(
        description="dotted path -> candidate values, e.g. indicators.ema9.params.period: [5, 8, 9]"
    )
    objective: str = Field(default="sharpe", pattern="^(sharpe|net_pnl|calmar|expectancy)$")
    max_runs: int = Field(default=200, ge=1, le=2000)
    windows: dict[str, int] | None = Field(
        default=None, description="walk_forward only: {train_days, test_days, step_days}"
    )
    base: BacktestIn | None = None


class OptJobOut(BaseModel):
    id: int
    strategy_version_id: int
    instrument_id: int
    kind: OptimizationKind
    param_space: dict[str, Any]
    objective: str
    windows: dict[str, Any] | None
    status: JobStatus
    progress_pct: float
    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None
    best_backtest_job_id: int | None
    config: dict[str, Any]


class OptRowOut(BaseModel):
    rank: int
    params: dict[str, Any]
    metrics: dict[str, Any]
    window: dict[str, Any] | None
    is_oos: bool


# ------------------------------------------------------------------ helpers
def _ist_span(start: date, end: date) -> tuple[datetime, datetime]:
    s = ensure_utc(datetime.combine(start, datetime.min.time(), tzinfo=IST))
    e = ensure_utc(datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=IST))
    if e <= s:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "end must be on/after start")
    return s, e


async def _version(db: DB, user: User, version_id: int) -> StrategyVersion:
    from api.routers.strategies import _owned_version

    return await _owned_version(db, user, version_id)


async def _enqueue(state: State, fn: str, *args: Any) -> None:
    pool = await create_pool(RedisSettings.from_dsn(state.settings.redis_url))
    try:
        await pool.enqueue_job(fn, *args)
    finally:
        await pool.aclose()


def _job_out(j: BacktestJob, has_result: bool = False) -> JobOut:
    return JobOut(
        id=j.id,
        strategy_version_id=j.strategy_version_id,
        instrument_id=j.instrument_id,
        timeframe=str(j.timeframe.value if hasattr(j.timeframe, "value") else j.timeframe),
        start_at=j.start_at,
        end_at=j.end_at,
        status=j.status,
        progress_pct=float(j.progress_pct or 0),
        config=j.config,
        config_hash=j.config_hash,
        seed=j.seed,
        label=j.label,
        queued_at=j.queued_at,
        started_at=j.started_at,
        finished_at=j.finished_at,
        error=j.error,
        has_result=has_result,
    )


async def _owned_job(db: DB, user: User, job_id: int) -> BacktestJob:
    j = await db.get(BacktestJob, job_id)
    if j is None or j.user_id != user.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "backtest job not found")
    return j


def _progress_from_redis(raw: str | bytes, fallback: float) -> float:
    """Worker writes either a bare number or {"pct": .., "message": ..}."""
    try:
        v = orjson.loads(raw)
        if isinstance(v, dict):
            return float(v.get("pct", fallback))
        return float(v)
    except (ValueError, TypeError):
        return fallback


# ------------------------------------------------------------------ backtests
@router.post("", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
async def create_backtest(body: BacktestIn, db: DB, state: State, user: User) -> JobOut:
    v = await _version(db, user, body.strategy_version_id)
    s, e = _ist_span(body.start, body.end)
    tf = body.timeframe or Timeframe(str(v.dsl.get("timeframe", "5m")))
    cfg = body.model_dump(mode="json")
    import hashlib

    cfg_hash = hashlib.sha256(
        orjson.dumps({**cfg, "dsl_hash": v.dsl_hash}, option=orjson.OPT_SORT_KEYS)
    ).hexdigest()
    j = BacktestJob(
        user_id=user.user_id,
        strategy_version_id=v.id,
        instrument_id=body.instrument_id,
        timeframe=tf,
        start_at=s,
        end_at=e,
        config=cfg,
        config_hash=cfg_hash,
        seed=body.seed,
        status=JobStatus.QUEUED,
        progress_pct=Decimal("0"),
        queued_at=utcnow(),
        requested_by=user.user_id,
        label=body.label,
    )
    db.add(j)
    await db.flush()
    await audit(
        db,
        user_id=user.user_id,
        action="backtest.create",
        entity_type="backtest_job",
        entity_id=j.id,
        after={"version": v.id},
    )
    await db.commit()
    await _enqueue(state, "run_backtest_job", j.id)
    return _job_out(j)


@router.get("", response_model=list[JobOut])
async def list_backtests(
    db: DB,
    user: User,
    strategy_version_id: int | None = None,
    status_filter: Annotated[JobStatus | None, Query(alias="status")] = None,
    limit: int = Query(default=50, ge=1, le=500),
) -> list[JobOut]:
    q = select(BacktestJob, BacktestResult.id).outerjoin(
        BacktestResult, BacktestResult.job_id == BacktestJob.id
    )
    q = (
        q.where(BacktestJob.user_id == user.user_id)
        .order_by(BacktestJob.queued_at.desc())
        .limit(limit)
    )
    if strategy_version_id is not None:
        q = q.where(BacktestJob.strategy_version_id == strategy_version_id)
    if status_filter is not None:
        q = q.where(BacktestJob.status == status_filter)
    return [_job_out(j, rid is not None) for j, rid in (await db.execute(q)).all()]


@router.get("/{job_id}", response_model=JobOut)
async def get_backtest(job_id: int, db: DB, state: State, user: User) -> JobOut:
    j = await _owned_job(db, user, job_id)
    has = (
        await db.execute(select(BacktestResult.id).where(BacktestResult.job_id == j.id))
    ).scalar_one_or_none()
    out = _job_out(j, has is not None)
    raw = await state.redis.get(f"backtest:{j.id}:progress")
    if raw and j.status == JobStatus.RUNNING:
        out.progress_pct = _progress_from_redis(raw, out.progress_pct)
    return out


@router.delete("/{job_id}", response_model=JobOut)
async def cancel_backtest(job_id: int, db: DB, state: State, user: User) -> JobOut:
    j = await _owned_job(db, user, job_id)
    if j.status in (JobStatus.QUEUED, JobStatus.RUNNING):
        await state.redis.set(f"backtest:{j.id}:cancel", "1", ex=3600)
        if j.status == JobStatus.QUEUED:
            j.status = JobStatus.CANCELLED
            j.finished_at = utcnow()
        await audit(
            db,
            user_id=user.user_id,
            action="backtest.cancel",
            entity_type="backtest_job",
            entity_id=j.id,
        )
        await db.commit()
    return _job_out(j)


@router.get("/{job_id}/results", response_model=ResultOut)
async def backtest_results(job_id: int, db: DB, user: User) -> ResultOut:
    j = await _owned_job(db, user, job_id)
    r = (
        await db.execute(select(BacktestResult).where(BacktestResult.job_id == j.id))
    ).scalar_one_or_none()
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no results yet (status {j.status.value})")
    return ResultOut(
        job=_job_out(j, True),
        metrics=r.metrics,
        equity_curve=r.equity_curve,
        drawdown_curve=r.drawdown_curve,
        monthly_table=r.monthly_table,
        assumptions=r.assumptions,
        data_hash=r.data_hash,
        engine_stats=r.engine_stats,
        warnings=list(r.warnings or []),
        elapsed_s=float(r.elapsed_s) if r.elapsed_s is not None else None,
    )


@router.get("/{job_id}/trades", response_model=list[TradeOut])
async def backtest_trades(
    job_id: int,
    db: DB,
    user: User,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=500, ge=1, le=5000),
) -> list[TradeOut]:
    j = await _owned_job(db, user, job_id)
    r = (
        await db.execute(select(BacktestResult).where(BacktestResult.job_id == j.id))
    ).scalar_one_or_none()
    if r is None:
        return []
    rows = await db.execute(
        select(BacktestTrade)
        .where(BacktestTrade.result_id == r.id)
        .order_by(BacktestTrade.entry_at)
        .offset(offset)
        .limit(limit)
    )
    return [
        TradeOut(
            id=t.id,
            instrument_id=t.instrument_id,
            side=str(t.side.value if hasattr(t.side, "value") else t.side),
            quantity=t.quantity,
            entry_at=t.entry_at,
            entry_price=t.entry_price,
            exit_at=t.exit_at,
            exit_price=t.exit_price,
            gross_pnl=t.gross_pnl,
            costs=t.costs,
            net_pnl=t.net_pnl,
            entry_reason=t.entry_reason,
            exit_reason=t.exit_reason,
            bars_held=t.bars_held,
            mae=t.mae,
            mfe=t.mfe,
        )
        for t in rows.scalars().all()
    ]


@router.get("/{job_id}/report")
async def backtest_report(job_id: int, db: DB, user: User) -> dict[str, str | None]:
    j = await _owned_job(db, user, job_id)
    r = (
        await db.execute(select(BacktestResult).where(BacktestResult.job_id == j.id))
    ).scalar_one_or_none()
    return {"markdown": r.report_md if r else None}


# ------------------------------------------------------------------ optimisation / walk-forward
def _opt_out(j: OptimizationJob) -> OptJobOut:
    return OptJobOut(
        id=j.id,
        strategy_version_id=j.strategy_version_id,
        instrument_id=j.instrument_id,
        kind=j.kind,
        param_space=j.param_space,
        objective=j.objective,
        windows=j.windows,
        status=j.status,
        progress_pct=float(j.progress_pct or 0),
        queued_at=j.queued_at,
        started_at=j.started_at,
        finished_at=j.finished_at,
        error=j.error,
        best_backtest_job_id=j.best_backtest_job_id,
        config=j.config,
    )


@router.post("/optimizations", response_model=OptJobOut, status_code=status.HTTP_202_ACCEPTED)
async def create_optimization(body: OptimizationIn, db: DB, state: State, user: User) -> OptJobOut:
    v = await _version(db, user, body.strategy_version_id)
    if body.kind == OptimizationKind.WALK_FORWARD and not body.windows:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "windows required for walk_forward"
        )
    base = body.base or BacktestIn(
        strategy_version_id=v.id, instrument_id=body.instrument_id, start=body.start, end=body.end
    )
    s, e = _ist_span(body.start, body.end)
    cfg = {
        **base.model_dump(mode="json"),
        "start_at": s.isoformat(),
        "end_at": e.isoformat(),
        "max_runs": body.max_runs,
    }
    j = OptimizationJob(
        user_id=user.user_id,
        strategy_version_id=v.id,
        instrument_id=body.instrument_id,
        kind=body.kind,
        param_space=body.param_space,
        objective=body.objective,
        windows=body.windows,
        config=cfg,
        status=JobStatus.QUEUED,
        progress_pct=Decimal("0"),
        queued_at=utcnow(),
    )
    db.add(j)
    await db.flush()
    await audit(
        db,
        user_id=user.user_id,
        action="optimization.create",
        entity_type="optimization_job",
        entity_id=j.id,
    )
    await db.commit()
    fn = (
        "run_walk_forward_job"
        if body.kind == OptimizationKind.WALK_FORWARD
        else "run_optimization_job"
    )
    await _enqueue(state, fn, j.id)
    return _opt_out(j)


@router.get("/optimizations", response_model=list[OptJobOut])
async def list_optimizations(
    db: DB, user: User, limit: int = Query(default=50, ge=1, le=500)
) -> list[OptJobOut]:
    q = (
        select(OptimizationJob)
        .where(OptimizationJob.user_id == user.user_id)
        .order_by(OptimizationJob.queued_at.desc())
        .limit(limit)
    )
    return [_opt_out(j) for j in (await db.execute(q)).scalars().all()]


@router.get("/optimizations/{job_id}", response_model=OptJobOut)
async def get_optimization(job_id: int, db: DB, state: State, user: User) -> OptJobOut:
    j = await db.get(OptimizationJob, job_id)
    if j is None or j.user_id != user.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "optimization not found")
    out = _opt_out(j)
    raw = await state.redis.get(f"optimization:{j.id}:progress")
    if raw and j.status == JobStatus.RUNNING:
        out.progress_pct = _progress_from_redis(raw, out.progress_pct)
    return out


@router.get("/optimizations/{job_id}/results", response_model=list[OptRowOut])
async def optimization_results(
    job_id: int, db: DB, user: User, limit: int = Query(default=500, ge=1, le=5000)
) -> list[OptRowOut]:
    j = await db.get(OptimizationJob, job_id)
    if j is None or j.user_id != user.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "optimization not found")
    rows = await db.execute(
        select(OptimizationResult)
        .where(OptimizationResult.job_id == j.id)
        .order_by(OptimizationResult.rank)
        .limit(limit)
    )
    return [
        OptRowOut(rank=r.rank, params=r.params, metrics=r.metrics, window=r.window, is_oos=r.is_oos)
        for r in rows.scalars().all()
    ]
