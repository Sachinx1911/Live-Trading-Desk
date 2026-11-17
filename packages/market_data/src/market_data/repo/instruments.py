"""Canonical instruments + per-provider mappings + F&O contract rows."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import Contract, Exchange, InstrumentMapping
from core.db.models import Instrument as InstrumentRow
from core.db.models._enums import ContractType, InstrumentType, Settlement
from core.models import AssetClass, Instrument, OptionType, Segment
from core.time import utcnow
from market_data.repo._lookup import exchange_id, provider_id, segment_id

_ASSET_TO_TYPE: dict[AssetClass, InstrumentType] = {
    AssetClass.STOCK: InstrumentType.EQUITY,
    AssetClass.INDEX: InstrumentType.INDEX,
    AssetClass.FUTURE: InstrumentType.FUTURE,
    AssetClass.OPTION: InstrumentType.OPTION,
    AssetClass.ETF: InstrumentType.ETF,
    AssetClass.FX: InstrumentType.CURRENCY,
    AssetClass.COMMODITY: InstrumentType.COMMODITY,
}

_TYPE_TO_ASSET = {v: k for k, v in _ASSET_TO_TYPE.items()}
_TYPE_TO_SEGMENT: dict[InstrumentType, Segment] = {
    InstrumentType.EQUITY: Segment.EQUITY,
    InstrumentType.ETF: Segment.EQUITY,
    InstrumentType.INDEX: Segment.INDEX,
    InstrumentType.FUTURE: Segment.FUTURES,
    InstrumentType.OPTION: Segment.OPTIONS,
    InstrumentType.CURRENCY: Segment.CURRENCY,
    InstrumentType.COMMODITY: Segment.COMMODITY,
}

TokenFn = Callable[[Instrument], str]


@dataclass
class SyncResult:
    provider: str
    new: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0
    id_map: dict[int, int] = field(default_factory=dict)  # provider-provisional id -> db id


def _default_token(ins: Instrument) -> str:
    return ins.symbol


async def upsert_instruments(
    session: AsyncSession,
    instruments: Sequence[Instrument],
    provider: str,
    token_of: TokenFn = _default_token,
    as_of: date | None = None,
) -> SyncResult:
    """Match on (exchange, symbol); update mutable fields; keep ids stable; write mappings
    and contract rows. Instruments whose segment has no seeded row are skipped."""
    res = SyncResult(provider=provider)
    pid = await provider_id(session, provider)
    today = as_of or utcnow().date()

    by_key: dict[tuple[str, str], Instrument] = {}
    for ins in instruments:
        by_key[(ins.exchange, ins.symbol)] = ins

    existing: dict[tuple[str, str], InstrumentRow] = {}
    q = select(InstrumentRow, Exchange.code).join(
        Exchange, Exchange.id == InstrumentRow.exchange_id
    )
    for existing_row, ex_code in (await session.execute(q)).all():
        existing[(ex_code, existing_row.symbol)] = existing_row

    derivatives: list[Instrument] = []
    for key, ins in by_key.items():
        try:
            seg_id = await segment_id(session, ins.exchange, ins.segment)
            ex_id = await exchange_id(session, ins.exchange)
            itype = _ASSET_TO_TYPE[ins.asset_class]
        except (LookupError, KeyError):
            res.skipped += 1
            continue
        row = existing.get(key)
        if row is None:
            row = InstrumentRow(
                exchange_id=ex_id,
                segment_id=seg_id,
                symbol=ins.symbol,
                name=ins.name,
                isin=ins.isin,
                instrument_type=itype,
                lot_size=ins.lot_size,
                tick_size=ins.tick_size,
                is_tradable=ins.is_active,
            )
            session.add(row)
            existing[key] = row
            res.new += 1
        else:
            changed = False
            for attr, val in (
                ("name", ins.name),
                ("isin", ins.isin),
                ("lot_size", ins.lot_size),
                ("tick_size", ins.tick_size),
                ("is_tradable", ins.is_active),
                ("segment_id", seg_id),
                ("instrument_type", itype),
            ):
                if getattr(row, attr) != val:
                    setattr(row, attr, val)
                    changed = True
            res.updated += changed
            res.unchanged += not changed
        if ins.is_derivative:
            derivatives.append(ins)
    await session.flush()

    for key, ins in by_key.items():
        mapped = existing.get(key)
        if mapped is None:
            continue
        row = mapped
        res.id_map[ins.instrument_id] = row.id
        token = token_of(ins)
        mq = select(InstrumentMapping).where(
            InstrumentMapping.provider_id == pid,
            InstrumentMapping.instrument_id == row.id,
            InstrumentMapping.valid_to.is_(None),
        )
        mapping = (await session.execute(mq)).scalar_one_or_none()
        if mapping is None:
            session.add(
                InstrumentMapping(
                    instrument_id=row.id,
                    provider_id=pid,
                    provider_symbol=ins.symbol,
                    provider_token=token,
                    valid_from=today,
                )
            )
        elif mapping.provider_token != token or mapping.provider_symbol != ins.symbol:
            mapping.valid_to = today
            session.add(
                InstrumentMapping(
                    instrument_id=row.id,
                    provider_id=pid,
                    provider_symbol=ins.symbol,
                    provider_token=token,
                    valid_from=today,
                )
            )

    for ins in derivatives:
        row = existing[(ins.exchange, ins.symbol)]
        under = existing.get((ins.exchange, ins.underlying_symbol or ""))
        if under is None or ins.expiry is None:
            continue
        c = await session.get(Contract, row.id)
        ctype = ContractType.OPTION if ins.segment == Segment.OPTIONS else ContractType.FUTURE
        if c is None:
            session.add(
                Contract(
                    instrument_id=row.id,
                    underlying_id=under.id,
                    expiry=ins.expiry,
                    strike=ins.strike if ctype == ContractType.OPTION else None,
                    option_type=ins.option_type if ctype == ContractType.OPTION else None,
                    contract_type=ctype,
                    settlement=Settlement.CASH,
                    multiplier=Decimal(1),
                )
            )
    await session.flush()
    return res


def _to_canonical(row: InstrumentRow, ex_code: str, contract: Contract | None) -> Instrument:
    itype = InstrumentType(row.instrument_type)
    return Instrument(
        instrument_id=row.id,
        exchange=ex_code,
        segment=_TYPE_TO_SEGMENT[itype],
        asset_class=_TYPE_TO_ASSET[itype],
        symbol=row.symbol,
        name=row.name,
        isin=row.isin,
        underlying_symbol=None,
        expiry=contract.expiry if contract else None,
        strike=contract.strike if contract else None,
        option_type=OptionType(contract.option_type) if contract and contract.option_type else None,
        lot_size=row.lot_size,
        tick_size=row.tick_size,
        is_active=row.is_tradable,
    )


async def get_instrument(session: AsyncSession, instrument_id: int) -> Instrument | None:
    q = (
        select(InstrumentRow, Exchange.code, Contract)
        .join(Exchange, Exchange.id == InstrumentRow.exchange_id)
        .outerjoin(Contract, Contract.instrument_id == InstrumentRow.id)
        .where(InstrumentRow.id == instrument_id)
    )
    r = (await session.execute(q)).first()
    return _to_canonical(r[0], r[1], r[2]) if r else None


async def get_by_symbol(session: AsyncSession, exchange: str, symbol: str) -> Instrument | None:
    q = (
        select(InstrumentRow, Exchange.code, Contract)
        .join(Exchange, Exchange.id == InstrumentRow.exchange_id)
        .outerjoin(Contract, Contract.instrument_id == InstrumentRow.id)
        .where(Exchange.code == exchange, InstrumentRow.symbol == symbol)
    )
    r = (await session.execute(q)).first()
    return _to_canonical(r[0], r[1], r[2]) if r else None


async def search(
    session: AsyncSession, query: str, limit: int = 20, exchange: str | None = None
) -> list[Instrument]:
    pattern = f"%{query.strip()}%"
    q = (
        select(InstrumentRow, Exchange.code, Contract)
        .join(Exchange, Exchange.id == InstrumentRow.exchange_id)
        .outerjoin(Contract, Contract.instrument_id == InstrumentRow.id)
        .where(or_(InstrumentRow.symbol.ilike(pattern), InstrumentRow.name.ilike(pattern)))
        .order_by(InstrumentRow.symbol)
        .limit(limit)
    )
    if exchange:
        q = q.where(Exchange.code == exchange)
    return [_to_canonical(r, c, k) for r, c, k in (await session.execute(q)).all()]


async def provider_token_for(
    session: AsyncSession, instrument_id: int, provider: str
) -> str | None:
    pid = await provider_id(session, provider)
    q = select(InstrumentMapping.provider_token).where(
        InstrumentMapping.instrument_id == instrument_id,
        InstrumentMapping.provider_id == pid,
        InstrumentMapping.valid_to.is_(None),
    )
    return (await session.execute(q)).scalar_one_or_none()
