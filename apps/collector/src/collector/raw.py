"""Raw tick archive to Parquet (ADR-010). Off unless COLLECT_RAW_TICKS=true."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import polars as pl

from core.models import Tick
from core.time import IST


class RawTickWriter:
    def __init__(self, root: Path, max_buffer: int = 5000) -> None:
        self.root = root
        self.max_buffer = max_buffer
        self._buf: list[dict[str, object]] = []

    def add(self, t: Tick) -> None:
        self._buf.append(
            {
                "instrument_id": t.instrument_id,
                "ts": t.ts,
                "provider_ts": t.provider_ts,
                "received_at": t.received_at,
                "ltp": float(t.ltp),
                "ltq": t.ltq,
                "volume": t.volume,
                "oi": t.oi,
                "bid": float(t.best_bid) if t.best_bid is not None else None,
                "ask": float(t.best_ask) if t.best_ask is not None else None,
                "bids": [[float(b.price), b.quantity, b.orders or 0] for b in t.bids],
                "asks": [[float(a.price), a.quantity, a.orders or 0] for a in t.asks],
                "provider": t.provider_id,
            }
        )
        if len(self._buf) >= self.max_buffer:
            self.flush()

    def flush(self) -> Path | None:
        if not self._buf:
            return None
        df = pl.DataFrame(self._buf)
        self._buf = []
        first: datetime = df["received_at"].min()  # type: ignore[assignment]
        local = first.astimezone(IST)
        out = self.root / f"date={local:%Y-%m-%d}" / f"provider={df['provider'][0]}"
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"ticks-{local:%H%M%S}-{first.microsecond:06d}.parquet"
        df.write_parquet(path, compression="zstd")
        return path
