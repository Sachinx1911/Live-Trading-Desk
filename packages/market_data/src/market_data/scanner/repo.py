"""Persistence for scan snapshots and saved scans."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import SavedScan, ScanSnapshot
from core.time import utcnow
from market_data.repo._lookup import provider_id
from market_data.scanner.presets import PRESETS


async def upsert_snapshot(
    session: AsyncSession, provider: str, as_of_date: date, rows: list[dict[str, Any]]
) -> ScanSnapshot:
    pid = await provider_id(session, provider)
    base = insert(ScanSnapshot).values(
        provider_id=pid,
        as_of_date=as_of_date,
        computed_at=utcnow(),
        instrument_count=len(rows),
        rows=rows,
    )
    stmt = base.on_conflict_do_update(
        index_elements=["provider_id", "as_of_date"],
        set_={"computed_at": utcnow(), "instrument_count": len(rows), "rows": rows},
    ).returning(ScanSnapshot.id)
    sid = (await session.execute(stmt)).scalar_one()
    await session.flush()
    return (await session.execute(select(ScanSnapshot).where(ScanSnapshot.id == sid))).scalar_one()


async def latest_snapshot(
    session: AsyncSession, provider: str, as_of: date | None = None
) -> ScanSnapshot | None:
    pid = await provider_id(session, provider)
    q = select(ScanSnapshot).where(ScanSnapshot.provider_id == pid)
    q = q.where(ScanSnapshot.as_of_date == as_of) if as_of else q
    q = q.order_by(ScanSnapshot.as_of_date.desc()).limit(1)
    return (await session.execute(q)).scalar_one_or_none()


async def snapshot_dates(session: AsyncSession, provider: str, limit: int = 30) -> list[date]:
    pid = await provider_id(session, provider)
    q = (
        select(ScanSnapshot.as_of_date)
        .where(ScanSnapshot.provider_id == pid)
        .order_by(ScanSnapshot.as_of_date.desc())
        .limit(limit)
    )
    return list((await session.execute(q)).scalars())


async def seed_presets(session: AsyncSession) -> int:
    """Insert any preset missing by name (idempotent). Returns the number inserted."""
    existing = set(
        (
            await session.execute(select(SavedScan.name).where(SavedScan.is_preset.is_(True)))
        ).scalars()
    )
    n = 0
    for p in PRESETS:
        if p["name"] in existing:
            continue
        session.add(
            SavedScan(
                user_id=None,
                name=p["name"],
                description=p["description"],
                filters=p["filters"],
                columns=p["columns"],
                sort=p["sort"],
                is_preset=True,
            )
        )
        n += 1
    await session.flush()
    return n


async def list_scans(session: AsyncSession, user_id: int) -> list[SavedScan]:
    q = (
        select(SavedScan)
        .where((SavedScan.is_preset.is_(True)) | (SavedScan.user_id == user_id))
        .order_by(SavedScan.is_preset.desc(), SavedScan.name)
    )
    return list((await session.execute(q)).scalars())


async def get_scan(session: AsyncSession, scan_id: int) -> SavedScan | None:
    return (
        await session.execute(select(SavedScan).where(SavedScan.id == scan_id))
    ).scalar_one_or_none()


async def create_scan(session: AsyncSession, user_id: int, data: dict[str, Any]) -> SavedScan:
    row = SavedScan(
        user_id=user_id,
        name=data["name"],
        description=data.get("description"),
        filters=data.get("filters") or {"all": [], "any": []},
        columns=data.get("columns") or [],
        sort=data.get("sort"),
        is_preset=False,
    )
    session.add(row)
    await session.flush()
    return row


async def update_scan(session: AsyncSession, row: SavedScan, data: dict[str, Any]) -> SavedScan:
    for k in ("name", "description", "filters", "columns", "sort"):
        if k in data and data[k] is not None:
            setattr(row, k, data[k])
    await session.flush()
    return row


async def delete_scan(session: AsyncSession, scan_id: int, user_id: int) -> bool:
    res = await session.execute(
        delete(SavedScan).where(
            SavedScan.id == scan_id, SavedScan.user_id == user_id, SavedScan.is_preset.is_(False)
        )
    )
    return bool(res.rowcount)  # type: ignore[attr-defined]
