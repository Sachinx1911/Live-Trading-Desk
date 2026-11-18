"""Deterministic markdown report for a BacktestResult. No AI, no adjectives: assumptions,
numbers, worst trades, monthly table. Same input → byte-identical output."""

from __future__ import annotations

from backtest.runner import BacktestResult


def _n(x: float | None, digits: int = 2, suffix: str = "") -> str:
    return "n/a" if x is None else f"{x:,.{digits}f}{suffix}"


def render_report(res: BacktestResult, *, worst_n: int = 5) -> str:
    a = res.assumptions
    m = res.metrics
    lines: list[str] = []
    lines.append(f"# Backtest report: {a.get('strategy_name', '')}")
    lines.append("")
    lines.append(f"- Config hash: `{res.config_hash[:16]}` · Data hash: `{res.data_hash[:16]}`")
    ins = a.get("instrument", {})
    rng = a.get("range", {})
    slip = a.get("slippage", {})
    lines.append(
        f"- Instrument: {ins.get('symbol')} ({ins.get('segment')}, lot {ins.get('lot_size')}) · "
        f"Timeframe: {a.get('timeframe')} · Range: {str(rng.get('start', ''))[:10]} to "
        f"{str(rng.get('end', ''))[:10]}"
    )
    lines.append(
        f"- Capital: Rs {float(a.get('initial_capital', 0)):,.0f} · Fill mode: {a.get('fill_mode')}"
        f" · Slippage: {slip.get('model')} {slip.get('bps')} bps · Costs: {a.get('cost_schedule')}"
        f" · Seed: {a.get('seed')}"
    )
    lines.append(f"- Bars: {res.bars} (warm-up {a.get('warmup_bars')})")
    if res.warnings:
        lines.append("")
        lines.append("**Warnings**")
        lines.extend(f"- {w}" for w in res.warnings)
    lines.append("")
    lines.append("## Metrics")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    rows = [
        ("Net return", f"Rs {_n(m.total_return)} ({_n(m.total_return_pct, 2, '%')})"),
        ("CAGR", _n(m.cagr_pct, 2, "%")),
        ("Trades (W/L)", f"{m.total_trades} ({m.wins}/{m.losses})"),
        ("Win rate", _n(m.win_rate_pct, 1, "%")),
        ("Profit factor", _n(m.profit_factor)),
        ("Expectancy / trade", f"Rs {_n(m.expectancy)}"),
        ("Avg win / avg loss", f"Rs {_n(m.avg_win)} / Rs {_n(m.avg_loss)}"),
        ("Payoff ratio", _n(m.payoff_ratio)),
        (
            "Max drawdown",
            f"Rs {_n(m.max_drawdown)} ({_n(m.max_drawdown_pct, 2, '%')}, "
            f"{m.max_dd_duration_days} days)",
        ),
        ("Sharpe / Sortino / Calmar", f"{_n(m.sharpe)} / {_n(m.sortino)} / {_n(m.calmar)}"),
        ("Max consecutive losses", str(m.max_consecutive_losses)),
        ("Exposure time", _n(m.exposure_time_pct, 1, "%")),
        ("Avg bars held", _n(m.avg_bars_held, 1)),
        ("Avg MAE / MFE (per unit)", f"{_n(m.avg_mae)} / {_n(m.avg_mfe)}"),
        ("Fees paid", f"Rs {_n(m.fees_total)}"),
        ("Final equity", f"Rs {_n(m.final_equity)}"),
    ]
    lines.extend(f"| {k} | {v} |" for k, v in rows)
    lines.append("")
    lines.append("## Engine")
    lines.append("")
    st = res.stats
    lines.append(
        f"- Signals: {st.get('signals')} · Orders: {st.get('orders')} · "
        f"Simulator rejections: {st.get('orders_rejected_by_simulator')}"
    )
    rej = st.get("risk_rejections") or {}
    if rej:
        lines.append("- Risk rejections: " + ", ".join(f"{k} x{v}" for k, v in sorted(rej.items())))
    gate = st.get("engine_gate") or {}
    if gate:
        lines.append("- Entry gate: " + ", ".join(f"{k} x{v}" for k, v in sorted(gate.items())))
    if res.trades:
        lines.append("")
        lines.append(f"## Worst {min(worst_n, len(res.trades))} trades")
        lines.append("")
        lines.append("| Entry | Exit | Side | Qty | Entry px | Exit px | Net | Reason |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for t in sorted(res.trades, key=lambda t: t.net_pnl)[:worst_n]:
            lines.append(
                f"| {t.entry_at:%Y-%m-%d %H:%M} | {t.exit_at:%Y-%m-%d %H:%M} | {t.side.value} | "
                f"{t.quantity} | {t.entry_price} | {t.exit_price} | {t.net_pnl} | "
                f"{t.exit_reason or ''} |"
            )
    if res.monthly_table:
        lines.append("")
        lines.append("## Monthly")
        lines.append("")
        lines.append("| Month | Equity | Return |")
        lines.append("|---|---|---|")
        for r in res.monthly_table:
            lines.append(f"| {r['month']} | Rs {r['equity']:,.2f} | {r['return_pct']:.2f}% |")
    lines.append("")
    return "\n".join(lines)
