"""Small cached lookups of reference rows (providers, exchanges, segments)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import DataProvider, Exchange, Market
from core.db.models import Segment as SegmentRow
from core.models.enums import Segment

_PROVIDER_IDS: dict[str, int] = {}
_EXCHANGE_IDS: dict[str, int] = {}
_SEGMENT_IDS: dict[tuple[str, str, str], int] = {}

# canonical Segment -> (market code, segment code) as seeded in migration 0002
SEGMENT_CODES: dict[Segment, tuple[str, str]] = {
    Segment.EQUITY: ("EQ", "CASH"),
    Segment.INDEX: ("EQ", "INDEX"),
    Segment.FUTURES: ("FO", "FUT"),
    Segment.OPTIONS: ("FO", "OPT"),
    Segment.CURRENCY: ("CD", "FUT"),
}


async def provider_id(session: AsyncSession, code: str) -> int:
    if code not in _PROVIDER_IDS:
        pid = (
            await session.execute(select(DataProvider.id).where(DataProvider.code == code))
        ).scalar_one_or_none()
        if pid is None:
            raise LookupError(f"data provider not seeded: {code!r}")
        _PROVIDER_IDS[code] = pid
    return _PROVIDER_IDS[code]


async def provider_code(session: AsyncSession, pid: int) -> str:
    for code, known in _PROVIDER_IDS.items():
        if known == pid:
            return code
    code = (
        await session.execute(select(DataProvider.code).where(DataProvider.id == pid))
    ).scalar_one()
    _PROVIDER_IDS[code] = pid
    return code


async def exchange_id(session: AsyncSession, code: str) -> int:
    if code not in _EXCHANGE_IDS:
        eid = (
            await session.execute(select(Exchange.id).where(Exchange.code == code))
        ).scalar_one_or_none()
        if eid is None:
            raise LookupError(f"exchange not seeded: {code!r}")
        _EXCHANGE_IDS[code] = eid
    return _EXCHANGE_IDS[code]


async def segment_id(session: AsyncSession, exchange_code: str, segment: Segment) -> int:
    try:
        market_code, seg_code = SEGMENT_CODES[segment]
    except KeyError as exc:
        raise LookupError(f"segment {segment} has no seeded row for {exchange_code}") from exc
    key = (exchange_code, market_code, seg_code)
    if key not in _SEGMENT_IDS:
        q = (
            select(SegmentRow.id)
            .join(Market, Market.id == SegmentRow.market_id)
            .join(Exchange, Exchange.id == Market.exchange_id)
            .where(
                Exchange.code == exchange_code,
                Market.code == market_code,
                SegmentRow.code == seg_code,
            )
        )
        sid = (await session.execute(q)).scalar_one_or_none()
        if sid is None:
            raise LookupError(f"segment not seeded: {key}")
        _SEGMENT_IDS[key] = sid
    return _SEGMENT_IDS[key]


def clear_cache() -> None:
    _PROVIDER_IDS.clear()
    _EXCHANGE_IDS.clear()
    _SEGMENT_IDS.clear()
