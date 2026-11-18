"""Historical data import: upload a file + mapping, see a dry-run report, then commit."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, ValidationError
from sqlalchemy import select

from api.audit import audit
from api.deps import DB, User
from core.db.models import DataImportJob
from market_data.imports import MAX_BYTES, ImportMapping, commit_import, parse_upload
from market_data.repo._lookup import provider_code

router = APIRouter(prefix="/historical/imports", tags=["historical"])


class ImportJobOut(BaseModel):
    id: int
    provider: str
    source_type: str
    source_uri: str | None
    status: str
    timeframe: str | None
    range_from: datetime | None
    range_to: datetime | None
    rows_read: int
    rows_written: int
    rows_rejected: int
    error: str | None
    instrument_scope: dict[str, Any]
    created_at: datetime
    finished_at: datetime | None


class ImportResponse(BaseModel):
    committed: bool
    report: dict[str, Any]
    job: ImportJobOut | None = None


async def _job_out(db: DB, j: DataImportJob) -> ImportJobOut:
    return ImportJobOut(
        id=j.id,
        provider=await provider_code(db, j.provider_id),
        source_type=j.source_type.value,
        source_uri=j.source_uri,
        status=j.status.value,
        timeframe=str(j.timeframe) if j.timeframe else None,
        range_from=j.range_from,
        range_to=j.range_to,
        rows_read=j.rows_read,
        rows_written=j.rows_written,
        rows_rejected=j.rows_rejected,
        error=j.error,
        instrument_scope=j.instrument_scope,
        created_at=j.created_at,
        finished_at=j.finished_at,
    )


@router.post("", response_model=ImportResponse)
async def upload_import(
    db: DB,
    user: User,
    file: Annotated[UploadFile, File()],
    mapping: Annotated[str, Form(description="ImportMapping as JSON")],
    commit: bool = False,
) -> ImportResponse:
    """Dry run by default (parse + validation report). `?commit=true` writes candles under
    provider `import` and records a data_import_jobs row."""
    try:
        m = ImportMapping.model_validate(json.loads(mapping))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"bad mapping: {exc}") from exc
    content = await file.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "file exceeds 50 MB")
    try:
        parsed = parse_upload(file.filename or "upload", content, m)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    if not commit:
        return ImportResponse(committed=False, report=parsed.report())
    if not user.has_role("owner"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only the owner can commit imports")
    try:
        res = await commit_import(db, parsed, user_id=user.user_id, source_uri=file.filename)
    except LookupError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    await audit(
        db,
        user_id=user.user_id,
        action="historical.import",
        entity_type="data_import_job",
        entity_id=res.job_id,
        after={
            "rows_written": res.rows_written,
            "status": res.status.value,
            "unresolved": res.unresolved_symbols,
            "file": file.filename,
        },
    )
    await db.commit()
    job = await db.get(DataImportJob, res.job_id)
    assert job is not None
    return ImportResponse(committed=True, report=parsed.report(), job=await _job_out(db, job))


@router.get("", response_model=list[ImportJobOut])
async def list_imports(db: DB, _: User, limit: int = 50) -> list[ImportJobOut]:
    rows = await db.execute(
        select(DataImportJob).order_by(DataImportJob.created_at.desc()).limit(limit)
    )
    return [await _job_out(db, j) for j in rows.scalars().all()]


@router.get("/{job_id}", response_model=ImportJobOut)
async def get_import(job_id: int, db: DB, _: User) -> ImportJobOut:
    j = await db.get(DataImportJob, job_id)
    if j is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "import job not found")
    return await _job_out(db, j)
