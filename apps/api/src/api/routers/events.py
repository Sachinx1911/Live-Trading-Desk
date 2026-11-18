"""Market events calendar (RBI, Fed, budget, expiry, results). Feeds the risk engine's
event block rule (ADR-013). Admin-maintained in Phase 3; imports later."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from api.audit import audit
from api.deps import DB, User
from core.db.models import Event, Exchange
from core.db.models._enums import EventType, Impact
from core.time import IST, ensure_utc

router = APIRouter(prefix="/events", tags=["events"])


class EventIn(BaseModel):
    exchange: str | None = "NSE"
    event_type: EventType
    title: str
    starts_at: datetime
    ends_at: datetime | None = None
    impact: Impact = Impact.HIGH
    blocks_trading: bool = True
    source: str | None = None


class EventOut(EventIn):
    id: int


def _out(e: Event, exchange_code: str | None) -> EventOut:
    return EventOut(
        id=e.id,
        exchange=exchange_code,
        event_type=e.event_type,
        title=e.title,
        starts_at=e.starts_at,
        ends_at=e.ends_at,
        impact=e.impact,
        blocks_trading=e.blocks_trading,
        source=e.source,
    )


@router.get("", response_model=list[EventOut])
async def list_events(
    db: DB, _: User, frm: date | None = None, to: date | None = None
) -> list[EventOut]:
    today = datetime.now(IST).date()
    frm = frm or today
    to = to or (today + timedelta(days=30))
    q = (
        select(Event, Exchange.code)
        .outerjoin(Exchange, Exchange.id == Event.exchange_id)
        .where(
            Event.starts_at >= ensure_utc(datetime.combine(frm, datetime.min.time(), tzinfo=IST))
        )
        .where(
            Event.starts_at
            < ensure_utc(datetime.combine(to + timedelta(days=1), datetime.min.time(), tzinfo=IST))
        )
        .order_by(Event.starts_at)
    )
    return [_out(e, code) for e, code in (await db.execute(q)).all()]


@router.post("", response_model=EventOut, status_code=status.HTTP_201_CREATED)
async def create_event(body: EventIn, db: DB, user: User) -> EventOut:
    ex_id = None
    if body.exchange:
        ex = (
            await db.execute(select(Exchange).where(Exchange.code == body.exchange))
        ).scalar_one_or_none()
        if ex is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "unknown exchange")
        ex_id = ex.id
    e = Event(
        exchange_id=ex_id,
        event_type=body.event_type,
        title=body.title,
        starts_at=ensure_utc(body.starts_at),
        ends_at=ensure_utc(body.ends_at) if body.ends_at else None,
        impact=body.impact,
        blocks_trading=body.blocks_trading,
        source=body.source,
    )
    db.add(e)
    await db.flush()
    await audit(
        db, user_id=user.user_id, action="event.create", entity_type="event", entity_id=e.id
    )
    await db.commit()
    return _out(e, body.exchange)


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(event_id: int, db: DB, user: User) -> None:
    e = await db.get(Event, event_id)
    if e is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "event not found")
    await db.delete(e)
    await audit(
        db, user_id=user.user_id, action="event.delete", entity_type="event", entity_id=event_id
    )
    await db.commit()
