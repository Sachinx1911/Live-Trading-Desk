"""Market scanner: field catalogue, presets, saved scans and running a scan against the
latest nightly snapshot. Filtering is deterministic (Polars) over stored metrics."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from api.audit import audit
from api.deps import DB, State, User
from core.time import utcnow
from market_data.scanner.filters import (
    DEFAULT_COLUMNS,
    FIELDS,
    OPS,
    ScanQuery,
    ScanQueryError,
    apply_query,
)
from market_data.scanner.repo import (
    create_scan,
    delete_scan,
    get_scan,
    latest_snapshot,
    list_scans,
    seed_presets,
    snapshot_dates,
    update_scan,
)

router = APIRouter(prefix="/scanner", tags=["scanner"])


class ScanField(BaseModel):
    name: str
    label: str
    type: str
    group: str
    unit: str | None = None
    description: str | None = None
    higher_is_better: bool | None = None
    values: list[str] | None = None


class ScanFieldsOut(BaseModel):
    fields: list[ScanField]
    ops: list[str]
    default_columns: list[str]


class Condition(BaseModel):
    field: str
    op: str
    value: Any = None


class Filters(BaseModel):
    all: list[Condition] = Field(default_factory=list)
    any: list[Condition] = Field(default_factory=list)


class Sort(BaseModel):
    field: str
    dir: str = "desc"


class ScanRunIn(BaseModel):
    filters: Filters = Field(default_factory=Filters)
    sort: Sort | None = None
    columns: list[str] | None = None
    offset: int = Field(0, ge=0)
    limit: int = Field(100, ge=1, le=2000)
    as_of: date | None = None


class ScanRunOut(BaseModel):
    as_of: date
    computed_at: datetime
    snapshot_age_s: int
    provider: str
    total: int
    columns: list[str]
    rows: list[dict[str, Any]]


class SavedScanIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str | None = None
    filters: Filters = Field(default_factory=Filters)
    sort: Sort | None = None
    columns: list[str] = Field(default_factory=lambda: list(DEFAULT_COLUMNS))


class SavedScanOut(BaseModel):
    id: int
    name: str
    description: str | None
    filters: Filters
    sort: Sort | None
    columns: list[str]
    is_preset: bool


class SnapshotStatus(BaseModel):
    provider: str
    as_of: date | None
    computed_at: datetime | None
    instrument_count: int
    available_dates: list[date]


def _out(row: Any) -> SavedScanOut:
    return SavedScanOut(
        id=row.id,
        name=row.name,
        description=row.description,
        filters=Filters.model_validate(row.filters or {}),
        sort=Sort.model_validate(row.sort) if row.sort else None,
        columns=list(row.columns or []),
        is_preset=row.is_preset,
    )


def _query(body: ScanRunIn) -> ScanQuery:
    spec = body.model_dump(exclude={"as_of"})
    if spec["columns"] is None:
        spec.pop("columns")
    try:
        return ScanQuery.from_dict(spec)
    except ScanQueryError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


@router.get("/fields", response_model=ScanFieldsOut)
async def fields(_: User) -> ScanFieldsOut:
    return ScanFieldsOut(
        fields=[ScanField(name=k, **v) for k, v in FIELDS.items()],
        ops=list(OPS),
        default_columns=list(DEFAULT_COLUMNS),
    )


@router.get("/presets", response_model=list[SavedScanOut])
async def presets(db: DB, _: User) -> list[SavedScanOut]:
    if await seed_presets(db):
        await db.commit()
    return [_out(r) for r in await list_scans(db, -1) if r.is_preset]


@router.get("/saved", response_model=list[SavedScanOut])
async def saved(db: DB, user: User) -> list[SavedScanOut]:
    if await seed_presets(db):
        await db.commit()
    return [_out(r) for r in await list_scans(db, user.user_id)]


@router.post("/saved", response_model=SavedScanOut, status_code=status.HTTP_201_CREATED)
async def create_saved(db: DB, user: User, body: SavedScanIn) -> SavedScanOut:
    _query(ScanRunIn(filters=body.filters, sort=body.sort, columns=body.columns))
    row = await create_scan(db, user.user_id, body.model_dump())
    await audit(
        db,
        user_id=user.user_id,
        action="scanner.saved.create",
        entity_type="saved_scan",
        entity_id=row.id,
        after={"name": row.name},
    )
    await db.commit()
    return _out(row)


@router.put("/saved/{scan_id}", response_model=SavedScanOut)
async def update_saved(db: DB, user: User, scan_id: int, body: SavedScanIn) -> SavedScanOut:
    row = await get_scan(db, scan_id)
    if row is None or row.is_preset or row.user_id != user.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "saved scan not found")
    _query(ScanRunIn(filters=body.filters, sort=body.sort, columns=body.columns))
    row = await update_scan(db, row, body.model_dump())
    await db.commit()
    return _out(row)


@router.delete("/saved/{scan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_saved(db: DB, user: User, scan_id: int) -> None:
    if not await delete_scan(db, scan_id, user.user_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "saved scan not found")
    await db.commit()


@router.post("/run", response_model=ScanRunOut)
async def run(db: DB, state: State, _: User, body: ScanRunIn) -> ScanRunOut:
    q = _query(body)
    provider = state.settings.default_market_data_provider
    snap = await latest_snapshot(db, provider, body.as_of)
    if snap is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "no scanner snapshot yet; run POST /scanner/snapshot"
        )
    rows, total = apply_query(snap.rows, q)
    return ScanRunOut(
        as_of=snap.as_of_date,
        computed_at=snap.computed_at,
        snapshot_age_s=int((utcnow() - snap.computed_at).total_seconds()),
        provider=provider,
        total=total,
        columns=list(q.columns),
        rows=rows,
    )


@router.get("/snapshot", response_model=SnapshotStatus)
async def snapshot(db: DB, state: State, _: User) -> SnapshotStatus:
    provider = state.settings.default_market_data_provider
    snap = await latest_snapshot(db, provider)
    return SnapshotStatus(
        provider=provider,
        as_of=snap.as_of_date if snap else None,
        computed_at=snap.computed_at if snap else None,
        instrument_count=snap.instrument_count if snap else 0,
        available_dates=await snapshot_dates(db, provider),
    )


@router.post("/snapshot", status_code=status.HTTP_202_ACCEPTED)
async def recompute(db: DB, state: State, user: User, as_of: date | None = None) -> dict[str, str]:
    if not user.has_role("owner"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "owner only")
    pool = await create_pool(RedisSettings.from_dsn(state.settings.redis_url))
    try:
        await pool.enqueue_job("compute_scan_snapshot", as_of.isoformat() if as_of else None)
    finally:
        await pool.aclose()
    await audit(
        db,
        user_id=user.user_id,
        action="scanner.snapshot.enqueue",
        entity_type="scan_snapshot",
        after={"as_of": str(as_of)},
    )
    await db.commit()
    return {"status": "queued"}
