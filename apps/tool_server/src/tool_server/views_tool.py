"""`record_view` tool (Mark 1 Stage 4.6 hook): JARVIS states a market view and the tool server
stores it with OUR reference price in `ai_observations`, so it can be scored later.

Registered here, in the tool-server app, not in `packages/protocols`: the paper trader imports
`protocols`, and an import-linter contract keeps `market_data.views` out of everything the
trader can reach (observations must never feed trading, ADR-009). It only appends one
measurement row and has no trading effect, so it is green (T0) with `writes=True`.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from market_data.views.service import RecordViewIn, ViewRefused, record_view
from protocols.actions import REGISTRY
from protocols.catalogue import ToolResult, ToolSpec, register_tool
from protocols.context import ActionContext
from protocols.registry import ActionError

CALLER = "jarvis"  # the tool server only serves the assistant; manual entries use the API


class RecordViewArgs(BaseModel):
    """What JARVIS may send. No price except its own invalidation level; the caller is set by
    the server."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    symbol: str = Field(min_length=1, max_length=40)
    exchange: str = Field("NSE", min_length=2, max_length=10)
    direction: Literal["up", "down", "sideways"]
    horizon_days: int = Field(ge=1, le=250, description="Horizon in NSE trading days")
    confidence: Decimal = Field(ge=0, le=1, max_digits=4, decimal_places=3)
    invalidation: str | None = Field(None, max_length=500)
    invalidation_price: Decimal | None = Field(None, gt=0, max_digits=14, decimal_places=4)
    statement: str | None = Field(None, max_length=4000)
    mode: str | None = Field(None, max_length=20, pattern=r"^[a-z0-9_.-]+$")


class RecordViewOutModel(ToolResult):
    observation_id: int
    due_date: str
    ref_price: str
    warnings: list[str]


@REGISTRY.register(
    "record_view",
    "Record a market view JARVIS stated (direction, horizon, confidence, invalidation) with the "
    "platform's own reference price, to be scored at the due date. Measurement only; never "
    "read by any strategy, risk check or order path.",
    "green",
    RecordViewArgs,
)
async def record_view_action(ctx: ActionContext, args: RecordViewArgs) -> dict[str, Any]:
    data = RecordViewIn(caller=CALLER, **args.model_dump())
    try:
        out = await record_view(
            ctx.session(), ctx.redis, ctx.settings, data, now=ctx.now(), commit=False
        )
    except ViewRefused as exc:
        raise ActionError(f"{exc.code}: {exc}") from exc
    return {
        "observation_id": out.observation_id,
        "symbol": out.symbol,
        "direction": out.direction,
        "horizon_days": out.horizon_days,
        "due_date": out.due_date.isoformat(),
        "ref_price": str(out.ref_price),
        "ref_ts": out.ref_ts.isoformat(),
        "warnings": out.warnings,
        "summary": (
            f"view #{out.observation_id} recorded: {out.symbol} {out.direction} over "
            f"{out.horizon_days} trading days, reference {out.ref_price} ({out.ref_freshness}), "
            f"due {out.due_date.isoformat()}"
        ),
        "source": out.ref_source,
        "freshness": out.ref_freshness,
        "is_demo": out.is_demo,
    }


register_tool(
    ToolSpec(
        name="record_view",
        action="record_view",
        purpose="Record a stated market view so it can be scored later.",
        example={
            "symbol": "NIFTY",
            "direction": "up",
            "horizon_days": 5,
            "confidence": "0.65",
            "invalidation": "view wrong below 25,000",
            "invalidation_price": "25000",
        },
        output_model=RecordViewOutModel,
        writes=True,
    )
)
