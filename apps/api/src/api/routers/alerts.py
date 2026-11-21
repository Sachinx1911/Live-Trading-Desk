"""Proactive alerts (Mark 1 Stage 3.2): read and acknowledge. Alerts are produced by the
worker's alert job and by the paper trader; nothing here creates one."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select, update

from api.audit import audit
from api.deps import DB, User
from core.db.models import Alert
from core.time import ensure_utc, utcnow

router = APIRouter(prefix="/alerts", tags=["alerts"])


class AlertOut(BaseModel):
    id: int
    ts: datetime
    kind: str
    severity: str
    title: str
    message: str
    data: dict[str, Any]
    dedup_key: str
    instrument_id: int | None
    delivered: dict[str, Any]
    acknowledged_at: datetime | None


class UnreadCount(BaseModel):
    unread: int
    critical: int


class AckAllOut(BaseModel):
    acknowledged: int


def _out(a: Alert) -> AlertOut:
    return AlertOut(
        id=a.id,
        ts=a.ts,
        kind=a.kind,
        severity=a.severity,
        title=a.title,
        message=a.message,
        data=a.data,
        dedup_key=a.dedup_key,
        instrument_id=a.instrument_id,
        delivered=a.delivered,
        acknowledged_at=a.acknowledged_at,
    )


@router.get("", response_model=list[AlertOut])
async def list_alerts(
    db: DB,
    _: User,
    since: datetime | None = None,
    unacknowledged: bool = False,
    kind: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[AlertOut]:
    q = select(Alert).order_by(Alert.ts.desc(), Alert.id.desc()).limit(limit)
    if since is not None:
        if since.tzinfo is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "since needs a timezone")
        q = q.where(Alert.ts >= ensure_utc(since))
    if unacknowledged:
        q = q.where(Alert.acknowledged_at.is_(None))
    if kind:
        q = q.where(Alert.kind == kind)
    return [_out(a) for a in (await db.execute(q)).scalars().all()]


@router.get("/unread-count", response_model=UnreadCount)
async def unread_count(db: DB, _: User) -> UnreadCount:
    row = (
        await db.execute(
            select(
                func.count(Alert.id),
                func.count(Alert.id).filter(Alert.severity == "critical"),
            ).where(Alert.acknowledged_at.is_(None))
        )
    ).one()
    return UnreadCount(unread=int(row[0]), critical=int(row[1]))


@router.post("/ack-all", response_model=AckAllOut)
async def ack_all(db: DB, user: User) -> AckAllOut:
    now = utcnow()
    res = await db.execute(
        update(Alert).where(Alert.acknowledged_at.is_(None)).values(acknowledged_at=now)
    )
    n = int(getattr(res, "rowcount", 0) or 0)
    await audit(
        db, user_id=user.user_id, action="alert.ack_all", entity_type="alert", after={"n": n}
    )
    await db.commit()
    return AckAllOut(acknowledged=n)


@router.post("/{alert_id}/ack", response_model=AlertOut)
async def ack(alert_id: int, db: DB, user: User) -> AlertOut:
    a = await db.get(Alert, alert_id)
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "alert not found")
    if a.acknowledged_at is None:
        a.acknowledged_at = utcnow()
        await audit(
            db, user_id=user.user_id, action="alert.ack", entity_type="alert", entity_id=a.id
        )
        await db.commit()
    return _out(a)
