"""Backtest configuration: everything that can change a result is here, hashed and frozen
into the result as `assumptions`, so two runs with the same hash are comparable."""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.models import Instrument, Timeframe
from core.time import ensure_utc
from risk.limits import RiskLimits
from strategy.dsl.schema import StrategyDocument

FillMode = Literal["next_bar_open", "bar_close"]


class SlippageConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    model: Literal["fixed_bps", "spread_aware"] = "fixed_bps"
    bps: float = Field(default=5.0, ge=0)
    size_impact_per_lot: float = Field(default=0.5, ge=0)


class CostRowSpec(BaseModel):
    """A `cost_schedules` row as plain data (see execution.costs.RowSchedule)."""

    model_config = ConfigDict(frozen=True)

    product: str
    charge_type: str
    side: str
    rate_type: str
    rate: str
    cap: str | None = None
    effective_from: str  # YYYY-MM-DD
    effective_to: str | None = None


def set_path(doc: dict[str, Any], path: str, value: Any) -> None:
    """Set `a.b.c` inside nested dicts, creating intermediate dicts. Integer keys index lists."""
    parts = path.split(".")
    cur: Any = doc
    for key in parts[:-1]:
        if isinstance(cur, list):
            cur = cur[int(key)]
        else:
            cur = cur.setdefault(key, {})
    last = parts[-1]
    if isinstance(cur, list):
        cur[int(last)] = value
    else:
        cur[last] = value


class BacktestConfig(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    strategy_version_id: int
    dsl: dict[str, Any]
    instrument: Instrument
    start: datetime
    end: datetime
    timeframe: Timeframe | None = Field(
        default=None, description="Overrides the DSL primary timeframe when set"
    )
    initial_capital: Decimal = Decimal("100000")
    risk_limits: RiskLimits = RiskLimits()
    slippage: SlippageConfig = SlippageConfig()
    cost_schedule: Literal["static", "rows"] = "static"
    cost_rows: list[CostRowSpec] = []
    seed: int = 42
    fill_mode: FillMode = Field(
        default="next_bar_open",
        description=(
            "next_bar_open: a signal on a closed bar fills at the NEXT bar's open (one bar of "
            "execution delay, the honest default). bar_close: fills at the signalling bar's "
            "close - optimistic, for diagnostics only."
        ),
    )
    param_overrides: dict[str, Any] = Field(
        default_factory=dict,
        description="Dotted paths into the DSL dict, e.g. 'indicators.ema9.params.period': 12",
    )
    lot_size: int | None = Field(default=None, ge=1, description="Overrides instrument.lot_size")
    label: str = ""
    keep_bar_equity: bool = False
    engine_version: str = "backtest-1.0"

    @field_validator("start", "end", mode="before")
    @classmethod
    def _utc(cls, v: datetime | str) -> datetime:
        return ensure_utc(v)

    # ------------------------------------------------------------------ derived
    def effective_dsl(self) -> dict[str, Any]:
        d = copy.deepcopy(self.dsl)
        for path, value in self.param_overrides.items():
            set_path(d, path, value)
        return d

    def document(self) -> StrategyDocument:
        return StrategyDocument.model_validate(self.effective_dsl())

    @property
    def effective_timeframe(self) -> Timeframe:
        return self.timeframe or Timeframe(self.document().timeframe)

    @property
    def effective_lot_size(self) -> int:
        return self.lot_size or self.instrument.lot_size

    def with_overrides(
        self, overrides: dict[str, Any], *, label: str | None = None
    ) -> BacktestConfig:
        merged = {**self.param_overrides, **overrides}
        return self.model_copy(update={"param_overrides": merged, "label": label or self.label})

    def assumptions(self) -> dict[str, Any]:
        doc = self.document()
        return {
            "engine_version": self.engine_version,
            "strategy_version_id": self.strategy_version_id,
            "strategy_name": doc.name,
            "instrument": {
                "id": self.instrument.instrument_id,
                "symbol": self.instrument.symbol,
                "segment": self.instrument.segment.value,
                "lot_size": self.effective_lot_size,
                "tick_size": str(self.instrument.tick_size),
            },
            "timeframe": self.effective_timeframe.value,
            "range": {"start": self.start.isoformat(), "end": self.end.isoformat()},
            "initial_capital": str(self.initial_capital),
            "risk_limits": json.loads(self.risk_limits.model_dump_json()),
            "slippage": self.slippage.model_dump(),
            "cost_schedule": self.cost_schedule,
            "cost_rows": [r.model_dump() for r in self.cost_rows],
            "seed": self.seed,
            "fill_mode": self.fill_mode,
            "param_overrides": self.param_overrides,
            "session": doc.session.model_dump(),
            "closed_bars_only": True,
            "stop_target_check": "bar high/low on closed bars (engine monitor_levels)",
        }

    def config_hash(self) -> str:
        payload = {"assumptions": self.assumptions(), "dsl": self.effective_dsl()}
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()
