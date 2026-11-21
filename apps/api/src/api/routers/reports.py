"""Stored daily reports (Mark 1 Stage 3.3 / 3.7: evening brief). Generation runs in the
worker; this router only reads rows and enqueues jobs."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select

from api.audit import audit
from api.deps import DB, State, User
from core.db.models import DailyReport

router = APIRouter(prefix="/reports", tags=["reports"])


class DailyReportOut(BaseModel):
    report_date: date
    kind: str
    content: dict[str, Any]
    text_md: str
    delivered: dict[str, Any]
    created_at: datetime


class DailyReportSummary(BaseModel):
    report_date: date
    kind: str
    created_at: datetime


class GenerateIn(BaseModel):
    day: date | None = None
    send: bool = False


def _out(r: DailyReport) -> DailyReportOut:
    return DailyReportOut(
        report_date=r.report_date,
        kind=r.kind,
        content=r.content,
        text_md=r.text_md,
        delivered=r.delivered,
        created_at=r.created_at,
    )


@router.get("/daily", response_model=list[DailyReportSummary])
async def list_daily(
    db: DB, user: User, limit: int = Query(default=60, ge=1, le=365)
) -> list[DailyReportSummary]:
    rows = (
        await db.execute(
            select(DailyReport.report_date, DailyReport.kind, DailyReport.created_at)
            .order_by(DailyReport.report_date.desc())
            .limit(limit)
        )
    ).all()
    return [DailyReportSummary(report_date=d, kind=k, created_at=c) for d, k, c in rows]


@router.get("/daily/latest", response_model=DailyReportOut)
async def latest_daily(db: DB, user: User) -> DailyReportOut:
    r = (
        await db.execute(select(DailyReport).order_by(DailyReport.report_date.desc()).limit(1))
    ).scalar_one_or_none()
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no report generated yet")
    return _out(r)


@router.get("/daily/{day}", response_model=DailyReportOut)
async def get_daily(day: date, db: DB, user: User) -> DailyReportOut:
    r = (
        await db.execute(
            select(DailyReport).where(DailyReport.report_date == day, DailyReport.kind == "eod")
        )
    ).scalar_one_or_none()
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no report for {day}")
    return _out(r)


@router.post("/daily/generate", status_code=status.HTTP_202_ACCEPTED)
async def generate_daily(body: GenerateIn, db: DB, user: User, state: State) -> dict[str, Any]:
    if not user.has_role("owner"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only the owner can generate reports")
    pool = await create_pool(RedisSettings.from_dsn(state.settings.redis_url))
    try:
        await pool.enqueue_job(
            "generate_evening_brief", body.day.isoformat() if body.day else None, body.send
        )
    finally:
        await pool.aclose()
    await audit(
        db,
        user_id=user.user_id,
        action="report.generate",
        entity_type="daily_report",
        entity_id=None,
        after={"day": body.day.isoformat() if body.day else None, "send": body.send},
    )
    await db.commit()
    return {"queued": True, "day": body.day.isoformat() if body.day else None}
