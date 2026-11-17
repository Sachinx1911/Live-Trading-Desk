"""Which instruments the collector follows. Configured by symbols; resolved to DB ids."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from core.models import Instrument
from market_data.repo.instruments import get_by_symbol


@dataclass
class Tracked:
    instruments: list[Instrument] = field(default_factory=list)
    chain_underlyings: list[Instrument] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    @property
    def ids(self) -> list[int]:
        return [i.instrument_id for i in self.instruments]


async def resolve(
    session: AsyncSession, exchange: str, symbols: list[str], chain_symbols: list[str]
) -> Tracked:
    t = Tracked()
    for sym in symbols:
        ins = await get_by_symbol(session, exchange, sym)
        (t.instruments.append(ins) if ins else t.missing.append(sym))
    for sym in chain_symbols:
        ins = await get_by_symbol(session, exchange, sym)
        if ins:
            t.chain_underlyings.append(ins)
            if ins.instrument_id not in t.ids:
                t.instruments.append(ins)
        else:
            t.missing.append(sym)
    return t


def parse_symbols(raw: str) -> list[str]:
    return [s.strip().upper() for s in raw.split(",") if s.strip()]
