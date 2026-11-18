"""Performance metrics from closed trades and a daily equity curve. Edge cases (no trades,
zero variance) yield None rather than NaN so results serialise cleanly."""

from __future__ import annotations

import itertools
import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from backtest.runner import TradeRecord

TRADING_DAYS = 252


@dataclass(frozen=True)
class Metrics:
    total_return: float | None
    total_return_pct: float | None
    cagr_pct: float | None
    win_rate_pct: float | None
    profit_factor: float | None
    max_drawdown: float | None
    max_drawdown_pct: float | None
    max_dd_duration_days: int | None
    sharpe: float | None
    sortino: float | None
    calmar: float | None
    expectancy: float | None
    avg_win: float | None
    avg_loss: float | None
    payoff_ratio: float | None
    total_trades: int
    wins: int
    losses: int
    max_consecutive_losses: int
    exposure_time_pct: float | None
    avg_bars_held: float | None
    avg_mae: float | None
    avg_mfe: float | None
    fees_total: float
    turnover: float
    final_equity: float
    initial_capital: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _f(x: Decimal | float | int | None) -> float | None:
    return None if x is None else float(x)


def _std(xs: Sequence[float]) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    m = sum(xs) / n
    return math.sqrt(sum((v - m) ** 2 for v in xs) / (n - 1))


def drawdown_curve(equity: Sequence[tuple[datetime, Decimal]]) -> list[tuple[datetime, float]]:
    peak: Decimal | None = None
    out: list[tuple[datetime, float]] = []
    for ts, eq in equity:
        peak = eq if peak is None or eq > peak else peak
        out.append((ts, float((eq - peak) / peak * 100) if peak else 0.0))
    return out


def max_drawdown(equity: Sequence[tuple[datetime, Decimal]]) -> tuple[float, float, int]:
    """(abs drawdown, pct drawdown, longest underwater duration in days)."""
    peak: Decimal | None = None
    peak_ts: datetime | None = None
    worst = Decimal(0)
    worst_pct = 0.0
    longest = 0
    for ts, eq in equity:
        if peak is None or eq > peak:
            peak, peak_ts = eq, ts
        dd = (peak - eq) if peak is not None else Decimal(0)
        if dd > worst:
            worst = dd
            worst_pct = float(dd / peak * 100) if peak else 0.0
        if peak_ts is not None and eq < peak:
            longest = max(longest, (ts - peak_ts).days)
    return float(worst), worst_pct, longest


def daily_returns(equity: Sequence[tuple[datetime, Decimal]]) -> list[float]:
    out: list[float] = []
    for (_, a), (_, b) in itertools.pairwise(equity):
        out.append(float((b - a) / a) if a else 0.0)
    return out


def monthly_table(equity: Sequence[tuple[datetime, Decimal]]) -> list[dict[str, Any]]:
    """Month-end equity and monthly % return."""
    if not equity:
        return []
    rows: list[dict[str, Any]] = []
    prev_eq = equity[0][1]
    cur_key: str | None = None
    last_eq = prev_eq
    start_eq = prev_eq
    for ts, eq in equity:
        key = ts.strftime("%Y-%m")
        if cur_key is None:
            cur_key, start_eq = key, prev_eq
        if key != cur_key:
            rows.append(
                {
                    "month": cur_key,
                    "equity": float(last_eq),
                    "return_pct": float((last_eq - start_eq) / start_eq * 100) if start_eq else 0.0,
                }
            )
            cur_key, start_eq = key, last_eq
        last_eq = eq
    if cur_key is not None:
        rows.append(
            {
                "month": cur_key,
                "equity": float(last_eq),
                "return_pct": float((last_eq - start_eq) / start_eq * 100) if start_eq else 0.0,
            }
        )
    return rows


def compute_metrics(
    trades: Sequence[TradeRecord],
    equity: Sequence[tuple[datetime, Decimal]],
    *,
    initial_capital: Decimal,
    bars_total: int,
    bars_in_position: int,
) -> Metrics:
    final = equity[-1][1] if equity else initial_capital
    total_ret = final - initial_capital
    total_ret_pct = float(total_ret / initial_capital * 100) if initial_capital else None
    cagr: float | None = None
    if len(equity) >= 2 and initial_capital > 0 and final > 0:
        years = max((equity[-1][0] - equity[0][0]).days, 1) / 365.25
        cagr = (float(final / initial_capital) ** (1 / years) - 1) * 100 if years > 0 else None

    nets = [float(t.net_pnl) for t in trades]
    wins = [x for x in nets if x > 0]
    losses = [x for x in nets if x < 0]
    n = len(nets)
    gross_win = sum(wins)
    gross_loss = -sum(losses)
    pf = (gross_win / gross_loss) if gross_loss > 0 else (None if gross_win == 0 else math.inf)
    if pf is not None and math.isinf(pf):
        pf = None  # all winners: undefined, surfaced as None rather than inf

    max_consec = 0
    run = 0
    for x in nets:
        run = run + 1 if x < 0 else 0
        max_consec = max(max_consec, run)

    dd_abs, dd_pct, dd_days = max_drawdown(equity)
    rets = daily_returns(equity)
    mean = sum(rets) / len(rets) if rets else 0.0
    sd = _std(rets)
    sharpe = (mean / sd * math.sqrt(TRADING_DAYS)) if sd > 0 else None
    downside = [r for r in rets if r < 0]
    dsd = math.sqrt(sum(r * r for r in downside) / len(rets)) if rets and downside else 0.0
    sortino = (mean / dsd * math.sqrt(TRADING_DAYS)) if dsd > 0 else None
    calmar = (cagr / dd_pct) if (cagr is not None and dd_pct > 0) else None

    avg_win = sum(wins) / len(wins) if wins else None
    avg_loss = sum(losses) / len(losses) if losses else None
    payoff = (avg_win / -avg_loss) if (avg_win is not None and avg_loss) else None
    expectancy = sum(nets) / n if n else None
    maes = [float(t.mae) for t in trades if t.mae is not None]
    mfes = [float(t.mfe) for t in trades if t.mfe is not None]
    bars_held = [t.bars_held for t in trades if t.bars_held is not None]

    return Metrics(
        total_return=float(total_ret),
        total_return_pct=total_ret_pct,
        cagr_pct=cagr,
        win_rate_pct=(len(wins) / n * 100) if n else None,
        profit_factor=pf,
        max_drawdown=dd_abs,
        max_drawdown_pct=dd_pct,
        max_dd_duration_days=dd_days,
        sharpe=sharpe,
        sortino=sortino,
        calmar=calmar,
        expectancy=expectancy,
        avg_win=avg_win,
        avg_loss=avg_loss,
        payoff_ratio=payoff,
        total_trades=n,
        wins=len(wins),
        losses=len(losses),
        max_consecutive_losses=max_consec,
        exposure_time_pct=(bars_in_position / bars_total * 100) if bars_total else None,
        avg_bars_held=(sum(bars_held) / len(bars_held)) if bars_held else None,
        avg_mae=(sum(maes) / len(maes)) if maes else None,
        avg_mfe=(sum(mfes) / len(mfes)) if mfes else None,
        fees_total=float(sum((t.costs for t in trades), Decimal(0))),
        turnover=float(
            sum((t.quantity * (t.entry_price + t.exit_price) for t in trades), Decimal(0))
        ),
        final_equity=float(final),
        initial_capital=float(initial_capital),
    )
