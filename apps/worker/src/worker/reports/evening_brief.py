"""Evening brief (Mark 1 Stage 3.3 + 3.7, no AI): the day in one structured record.

`build_content` turns gathered facts into a JSON-able dict (what is stored in
`daily_reports.content`); `render_markdown` turns that dict into the text sent to Telegram and
shown on /reports. Both are pure so they can be tested without a database. Every section says
when its data is missing instead of showing a number that was not measured.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

FULL_SESSION_MINUTES = 375  # 09:15-15:30 IST, one 1-minute bar each


@dataclass(frozen=True)
class IndexMove:
    symbol: str
    close: Decimal | None
    prev_close: Decimal | None

    @property
    def change(self) -> Decimal | None:
        if self.close is None or self.prev_close is None:
            return None
        return self.close - self.prev_close

    @property
    def change_pct(self) -> Decimal | None:
        if self.change is None or not self.prev_close:
            return None
        return (self.change / self.prev_close * 100).quantize(Decimal("0.01"))


@dataclass(frozen=True)
class PcrReading:
    symbol: str
    pcr: Decimal | None
    expiry: str | None
    as_of: datetime | None


@dataclass(frozen=True)
class AccountDay:
    account_id: int
    name: str
    cash: Decimal
    trades: int
    wins: int
    net_pnl: Decimal
    open_positions: int


@dataclass(frozen=True)
class Coverage:
    symbol: str
    bars: int
    expected: int

    @property
    def complete(self) -> bool:
        return self.expected > 0 and self.bars >= self.expected


@dataclass(frozen=True)
class Facts:
    day: date
    is_trading_day: bool
    indices: list[IndexMove] = field(default_factory=list)
    pcr: list[PcrReading] = field(default_factory=list)
    breadth: dict[str, Any] | None = None
    accounts: list[AccountDay] = field(default_factory=list)
    alerts_by_severity: dict[str, int] = field(default_factory=dict)
    rule_blocks: int = 0
    coverage: list[Coverage] = field(default_factory=list)
    next_trading_day: date | None = None
    expiries_next_7d: list[dict[str, str]] = field(default_factory=list)
    headlines: list[dict[str, str]] = field(default_factory=list)
    provider: str = ""


def _d(x: Decimal | None) -> str | None:
    return None if x is None else str(x)


def build_content(f: Facts) -> dict[str, Any]:
    return {
        "date": f.day.isoformat(),
        "is_trading_day": f.is_trading_day,
        "provider": f.provider,
        "indices": [
            {
                "symbol": m.symbol,
                "close": _d(m.close),
                "prev_close": _d(m.prev_close),
                "change": _d(m.change),
                "change_pct": _d(m.change_pct),
            }
            for m in f.indices
        ],
        "pcr": [
            {
                "symbol": p.symbol,
                "pcr": _d(p.pcr),
                "expiry": p.expiry,
                "as_of": p.as_of.isoformat() if p.as_of else None,
            }
            for p in f.pcr
        ],
        "breadth": f.breadth,
        "paper": [
            {**asdict(a), "cash": str(a.cash), "net_pnl": str(a.net_pnl)} for a in f.accounts
        ],
        "alerts": {"by_severity": f.alerts_by_severity, "rule_blocks": f.rule_blocks},
        "coverage": [{**asdict(c), "complete": c.complete} for c in f.coverage],
        "next_trading_day": f.next_trading_day.isoformat() if f.next_trading_day else None,
        "expiries_next_7d": f.expiries_next_7d,
        "headlines": f.headlines,
    }


def _signed(v: str | None, suffix: str = "") -> str:
    if v is None:
        return "n/a"
    return (v if v.startswith("-") else "+" + v) + suffix


def render_markdown(c: dict[str, Any]) -> str:
    lines = [f"*Evening brief · {c['date']}*"]
    if not c["is_trading_day"]:
        lines.append("Market closed today (NSE holiday or weekend).")
    lines.append("")
    lines.append("*Indices*")
    if not c["indices"]:
        lines.append("No index candles stored for today.")
    for m in c["indices"]:
        if m["close"] is None:
            lines.append(f"{m['symbol']}: no close stored")
        else:
            move = f"{_signed(m['change'])}, {_signed(m['change_pct'], '%')}"
            lines.append(f"{m['symbol']} {m['close']} ({move})")
    lines.append("")
    lines.append("*PCR at close*")
    for p in c["pcr"]:
        lines.append(
            f"{p['symbol']}: {p['pcr']} (expiry {p['expiry']})"
            if p["pcr"] is not None
            else f"{p['symbol']}: no chain snapshot"
        )
    if not c["pcr"]:
        lines.append("No chain snapshots stored.")
    lines.append("")
    lines.append("*Breadth (NIFTY 50)*")
    b = c["breadth"]
    if b is None:
        lines.append("Not computed for today.")
    else:
        lines.append(
            f"Advances {b['advances']} · declines {b['declines']} · unchanged {b['unchanged']}"
        )
        if b.get("above_ema200_pct") is not None:
            lines.append(f"Above EMA 200: {b['above_ema200_pct']}%")
        lines.append(f"52-week highs {b['new_52w_high']} · lows {b['new_52w_low']}")
    lines.append("")
    lines.append("*Paper trading*")
    if not c["paper"]:
        lines.append("No active paper account.")
    for a in c["paper"]:
        lines.append(
            f"{a['name']}: {a['trades']} trades, {a['wins']} wins, net {_signed(a['net_pnl'])} · "
            f"open positions {a['open_positions']} · cash {a['cash']}"
        )
    al = c["alerts"]
    sev = ", ".join(f"{k} {v}" for k, v in sorted(al["by_severity"].items())) or "none"
    lines.append(f"Alerts: {sev} · owner-rule blocks: {al['rule_blocks']}")
    lines.append("")
    lines.append("*Data completeness (1-minute bars)*")
    if not c["coverage"]:
        lines.append("No tracked symbols.")
    missing = [x for x in c["coverage"] if not x["complete"]]
    if c["coverage"] and not missing:
        lines.append(f"All {len(c['coverage'])} tracked symbols complete.")
    for x in missing:
        lines.append(f"{x['symbol']}: {x['bars']}/{x['expected']} bars")
    lines.append("")
    if c["next_trading_day"]:
        lines.append(f"*Next session* {c['next_trading_day']}")
    for e in c["expiries_next_7d"]:
        lines.append(f"Expiry {e['symbol']} {e['expiry']}")
    if c["headlines"]:
        lines.append("")
        lines.append("*Headlines*")
        for h in c["headlines"]:
            lines.append(f"• {h['title']} ({h['source']})")
    return "\n".join(lines).strip() + "\n"
