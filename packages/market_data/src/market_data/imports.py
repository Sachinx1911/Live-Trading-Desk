"""Historical data import: CSV / Excel / JSON / Parquet -> validated canonical candles.

Two phases so the UI can show a dry-run report first:
  parse_upload()  pure: bytes + mapping -> ImportParse (candles + validation report)
  commit_import() DB: resolve instruments, upsert candles (provider "import"), write the
                  data_import_jobs row with counts and manifest.
Raw rows are never trusted: every row is re-validated through the canonical Candle model.
"""

from __future__ import annotations

import hashlib
import io
import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal
from zoneinfo import ZoneInfo

import polars as pl
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import DataImportJob
from core.db.models._enums import ImportSourceType, JobStatus
from core.models import Candle, Timeframe
from core.time import utcnow
from market_data.quality import find_duplicates
from market_data.repo._lookup import provider_id
from market_data.repo.candles import upsert_candles
from market_data.repo.instruments import get_by_symbol

MAX_BYTES = 50 * 1024 * 1024
EXT_TO_SOURCE: dict[str, ImportSourceType] = {
    "csv": ImportSourceType.CSV,
    "txt": ImportSourceType.CSV,
    "xlsx": ImportSourceType.EXCEL,
    "xls": ImportSourceType.EXCEL,
    "json": ImportSourceType.JSON,
    "parquet": ImportSourceType.PARQUET,
}


class ImportMapping(BaseModel):
    """How to read the uploaded columns. Either `symbol_column` or `symbol` is required."""

    exchange: str = "NSE"
    timeframe: Timeframe = Timeframe.D1
    symbol: str | None = None
    symbol_column: str | None = None
    ts_column: str = "ts"
    ts_format: str | None = Field(default=None, description="strptime format; None = ISO/auto")
    timezone: str = "Asia/Kolkata"
    open_column: str = "open"
    high_column: str = "high"
    low_column: str = "low"
    close_column: str = "close"
    volume_column: str | None = "volume"
    oi_column: str | None = None
    provider: str = "import"
    source_label: str | None = None


@dataclass
class Rejection:
    row: int
    reason: str
    sample: dict[str, Any] = field(default_factory=dict)


@dataclass
class CoverageRow:
    symbol: str
    first_ts: datetime
    last_ts: datetime
    count: int


@dataclass
class ImportParse:
    source_type: ImportSourceType
    mapping: ImportMapping
    rows_read: int
    candles: list[Candle]  # instrument_id is 0 until commit resolves symbols
    symbols: dict[int, str]  # positional index -> symbol (parallel to candles)
    rejections: list[Rejection]
    coverage: list[CoverageRow]
    content_hash: str
    warnings: list[str] = field(default_factory=list)

    @property
    def manifest_hash(self) -> str:
        """Identity of this import: file content + mapping."""
        m = self.mapping.model_dump_json()
        return hashlib.sha256((self.content_hash + "|" + m).encode()).hexdigest()

    @property
    def rows_accepted(self) -> int:
        return len(self.candles)

    @property
    def rows_rejected(self) -> int:
        return len(self.rejections)

    def report(self, max_rejections: int = 50) -> dict[str, Any]:
        return {
            "source_type": self.source_type.value,
            "rows_read": self.rows_read,
            "rows_accepted": self.rows_accepted,
            "rows_rejected": self.rows_rejected,
            "rejections": [
                {"row": r.row, "reason": r.reason, "sample": r.sample}
                for r in self.rejections[:max_rejections]
            ],
            "coverage": [
                {
                    "symbol": c.symbol,
                    "first_ts": c.first_ts.isoformat(),
                    "last_ts": c.last_ts.isoformat(),
                    "count": c.count,
                }
                for c in self.coverage
            ],
            "warnings": self.warnings,
            "content_hash": self.content_hash,
            "manifest_hash": self.manifest_hash,
        }


def source_type_for(filename: str) -> ImportSourceType:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in EXT_TO_SOURCE:
        raise ValueError(f"unsupported file type '.{ext}' (csv, xlsx, json, parquet)")
    return EXT_TO_SOURCE[ext]


def _read_frame(source: ImportSourceType, content: bytes) -> pl.DataFrame:
    buf = io.BytesIO(content)
    if source == ImportSourceType.CSV:
        return pl.read_csv(buf, infer_schema_length=0)  # everything as str; we parse ourselves
    if source == ImportSourceType.EXCEL:
        return pl.read_excel(buf).cast(pl.String)
    if source == ImportSourceType.JSON:
        data = json.loads(content.decode("utf-8"))
        if isinstance(data, dict):
            # {"candles": [...]} or {"data": [...]}
            for key in ("candles", "data", "rows"):
                if isinstance(data.get(key), list):
                    data = data[key]
                    break
        if not isinstance(data, list):
            raise ValueError("JSON must be an array of objects")
        return pl.DataFrame(data).cast(pl.String) if data else pl.DataFrame()
    if source == ImportSourceType.PARQUET:
        return pl.read_parquet(buf).cast(pl.String)
    raise ValueError(f"unsupported source {source}")


def _parse_ts(raw: str, fmt: str | None, tz: ZoneInfo) -> datetime:
    s = raw.strip()
    if fmt:
        dt = datetime.strptime(s, fmt)  # noqa: DTZ007 - tz attached below
    else:
        if s.isdigit():  # epoch seconds or ms
            n = int(s)
            return datetime.fromtimestamp(n / 1000 if n > 10**11 else n, tz=UTC)
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return dt.astimezone(UTC)


def _dec(raw: str | None) -> Decimal:
    if raw is None or raw.strip() == "":
        raise InvalidOperation("empty")
    return Decimal(raw.strip().replace(",", ""))


def _int(raw: str | None) -> int | None:
    if raw is None or raw.strip() == "":
        return None
    return int(Decimal(raw.strip().replace(",", "")))


def parse_upload(filename: str, content: bytes, mapping: ImportMapping) -> ImportParse:
    if len(content) > MAX_BYTES:
        raise ValueError(f"file exceeds {MAX_BYTES // (1024 * 1024)} MB")
    if not mapping.symbol and not mapping.symbol_column:
        raise ValueError("mapping needs `symbol` or `symbol_column`")
    source = source_type_for(filename)
    df = _read_frame(source, content)
    content_hash = hashlib.sha256(content).hexdigest()
    required = [
        mapping.ts_column,
        mapping.open_column,
        mapping.high_column,
        mapping.low_column,
        mapping.close_column,
    ]
    if mapping.symbol_column:
        required.append(mapping.symbol_column)
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"missing columns: {missing}; available: {list(df.columns)}")
    tz = ZoneInfo(mapping.timezone)
    now = utcnow()
    candles: list[Candle] = []
    symbols: dict[int, str] = {}
    rejections: list[Rejection] = []
    seen: Counter[tuple[str, datetime]] = Counter()
    last_ts: dict[str, datetime] = {}
    warnings: list[str] = []
    for i, row in enumerate(df.iter_rows(named=True), start=1):
        sym = (row.get(mapping.symbol_column) if mapping.symbol_column else mapping.symbol) or ""
        sym = str(sym).strip().upper()
        sample = {k: row.get(k) for k in required}
        try:
            ts = _parse_ts(str(row[mapping.ts_column]), mapping.ts_format, tz)
        except (ValueError, TypeError, OverflowError) as exc:
            rejections.append(Rejection(i, f"bad timestamp: {exc}", sample))
            continue
        if not sym:
            rejections.append(Rejection(i, "empty symbol", sample))
            continue
        try:
            o, h, lo, c = (
                _dec(row[mapping.open_column]),
                _dec(row[mapping.high_column]),
                _dec(row[mapping.low_column]),
                _dec(row[mapping.close_column]),
            )
            vol = _int(row.get(mapping.volume_column)) if mapping.volume_column else None
            oi = _int(row.get(mapping.oi_column)) if mapping.oi_column else None
        except (InvalidOperation, ValueError, TypeError) as exc:
            rejections.append(Rejection(i, f"bad number: {exc}", sample))
            continue
        key = (sym, ts)
        seen[key] += 1
        if seen[key] > 1:
            rejections.append(Rejection(i, "duplicate (symbol, ts) within file", sample))
            continue
        if sym in last_ts and ts < last_ts[sym]:
            warnings.append(f"row {i}: {sym} timestamps not monotonic (sorted on commit)")
        last_ts[sym] = ts
        try:
            cd = Candle(
                instrument_id=0,
                timeframe=mapping.timeframe,
                ts=ts,
                open=o,
                high=h,
                low=lo,
                close=c,
                volume=vol or 0,
                oi=oi,
                provider_id=mapping.provider,
                provider_ts=ts,
                received_at=now,
                is_demo=False,
            )
        except ValueError as exc:
            rejections.append(Rejection(i, f"OHLC invalid: {exc}", sample))
            continue
        symbols[len(candles)] = sym
        candles.append(cd)
    # coverage per symbol
    cov: dict[str, list[datetime]] = {}
    for idx, cd in enumerate(candles):
        cov.setdefault(symbols[idx], []).append(cd.ts)
    coverage = [CoverageRow(s, min(v), max(v), len(v)) for s, v in sorted(cov.items())]
    if len(warnings) > 20:
        warnings = [*warnings[:20], f"... {len(warnings) - 20} more"]
    return ImportParse(
        source_type=source,
        mapping=mapping,
        rows_read=df.height,
        candles=candles,
        symbols=symbols,
        rejections=rejections,
        coverage=coverage,
        content_hash=content_hash,
        warnings=warnings,
    )


@dataclass
class CommitResult:
    job_id: int
    status: JobStatus
    rows_written: int
    unresolved_symbols: list[str]
    duplicates_after_merge: int


async def commit_import(
    session: AsyncSession,
    parse: ImportParse,
    *,
    user_id: int | None,
    source_uri: str | None,
    manifest_hash: str | None = None,
) -> CommitResult:
    """Resolve symbols to instruments, upsert, record the job. Commits nothing itself.
    The manifest (content + mapping) is unique: re-committing the same upload with the
    same mapping returns the earlier job instead of writing twice."""
    pid = await provider_id(session, parse.mapping.provider)
    manifest_hash = manifest_hash or parse.manifest_hash
    existing = (
        await session.execute(
            select(DataImportJob).where(DataImportJob.manifest_hash == manifest_hash)
        )
    ).scalar_one_or_none()
    if existing is not None:
        scope = existing.instrument_scope or {}
        return CommitResult(
            existing.id,
            existing.status,
            existing.rows_written,
            list(scope.get("unresolved", [])),
            int(scope.get("duplicates_after_merge", 0)),
        )
    job = DataImportJob(
        user_id=user_id,
        provider_id=pid,
        source_type=parse.source_type,
        source_uri=source_uri,
        manifest_hash=manifest_hash,
        instrument_scope={
            "symbols": [c.symbol for c in parse.coverage],
            "exchange": parse.mapping.exchange,
        },
        timeframe=parse.mapping.timeframe,
        range_from=min((c.first_ts for c in parse.coverage), default=None),
        range_to=max((c.last_ts for c in parse.coverage), default=None),
        status=JobStatus.RUNNING,
        rows_read=parse.rows_read,
        rows_written=0,
        rows_rejected=parse.rows_rejected,
        started_at=utcnow(),
    )
    session.add(job)
    await session.flush()
    ids: dict[str, int] = {}
    unresolved: list[str] = []
    for c in parse.coverage:
        ins = await get_by_symbol(session, parse.mapping.exchange, c.symbol)
        if ins is None:
            unresolved.append(c.symbol)
        else:
            ids[c.symbol] = ins.instrument_id
    resolved = [
        cd.model_copy(update={"instrument_id": ids[parse.symbols[i]]})
        for i, cd in enumerate(parse.candles)
        if parse.symbols[i] in ids
    ]
    resolved.sort(key=lambda c: (c.instrument_id, c.ts))
    dups = len(find_duplicates(resolved))
    written = await upsert_candles(session, resolved) if resolved else 0
    skipped = parse.rows_accepted - len(resolved)
    job.rows_written = written
    job.rows_rejected = parse.rows_rejected + skipped
    job.finished_at = utcnow()
    if written == 0:
        job.status = JobStatus.FAILED
        job.error = (
            f"no rows written; unresolved symbols: {unresolved}" if unresolved else "no rows"
        )
    elif unresolved or parse.rows_rejected:
        job.status = JobStatus.PARTIAL
        job.error = f"unresolved symbols: {unresolved}" if unresolved else None
    else:
        job.status = JobStatus.SUCCEEDED
    scope = dict(job.instrument_scope)
    scope.update({"unresolved": unresolved, "resolved_ids": ids, "duplicates_after_merge": dups})
    job.instrument_scope = scope
    await session.flush()
    return CommitResult(job.id, job.status, written, unresolved, dups)


SourceLiteral = Literal["csv", "excel", "json", "parquet"]
