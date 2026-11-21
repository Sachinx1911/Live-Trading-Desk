"""Measure how often the exchange's open-interest numbers actually change.

Polls one underlying's nearest-expiry option chain every few seconds and records each
moment the OI of any strike differs from the previous poll. Read-only: nothing is stored.
Run it during market hours:

    uv run python -m collector.oi_cadence --underlying NIFTY --minutes 20 --poll 15

The result tells us how short `COLLECT_CHAIN_INTERVAL_S` can usefully be.
"""

from __future__ import annotations

import argparse
import asyncio
import itertools
import statistics
from datetime import datetime, timedelta

from collector.main import Collector
from core.db import get_session_factory
from core.logging import get_logger
from core.settings import get_settings
from core.time import IST, utcnow
from market_data.binding import bind_provider
from market_data.repo.chains import expiries_for
from market_data.repo.instruments import get_by_symbol

log = get_logger("collector.oi_cadence")


def summarise(change_times: list[datetime]) -> dict[str, float | int | None]:
    """Gaps in seconds between successive OI changes."""
    gaps = [(b - a).total_seconds() for a, b in itertools.pairwise(change_times)]
    if not gaps:
        return {"changes": len(change_times), "min_s": None, "median_s": None, "max_s": None}
    return {
        "changes": len(change_times),
        "min_s": min(gaps),
        "median_s": statistics.median(gaps),
        "max_s": max(gaps),
    }


async def measure(underlying: str, minutes: int, poll_s: int) -> None:
    c = Collector(get_settings())
    await c._load_tokens()
    async with get_session_factory()() as db:
        await bind_provider(db, c.provider)
        und = await get_by_symbol(db, "NSE", underlying)
        if und is None:
            raise SystemExit(f"unknown underlying {underlying}")
        exps = await expiries_for(db, und.instrument_id, utcnow().astimezone(IST).date())
    if not exps:
        raise SystemExit("no unexpired contracts for that underlying")
    exp_dt = datetime.combine(exps[0], datetime.min.time(), tzinfo=IST).replace(hour=15, minute=30)
    if not c.cal.is_open(utcnow()):
        print("Market is closed: OI will not change now. Run this in market hours.")
    print(f"{underlying} expiry {exps[0]}: polling every {poll_s}s for {minutes} min")

    end = utcnow() + timedelta(minutes=minutes)
    prev: dict[tuple[str, str], int | None] | None = None
    changes: list[datetime] = []
    while utcnow() < end:
        try:
            snap = await c.provider.get_option_chain(und.instrument_id, exp_dt)
        except Exception as exc:
            print(f"{utcnow().astimezone(IST):%H:%M:%S} poll failed: {exc}")
            await asyncio.sleep(poll_s)
            continue
        cur = {(str(r.strike), str(r.option_type)): r.oi for r in snap.rows}
        now = utcnow()
        if prev is not None and cur != prev:
            n = sum(1 for k, v in cur.items() if prev.get(k) != v)
            changes.append(now)
            gap = f"{(now - changes[-2]).total_seconds():.0f}s" if len(changes) > 1 else "first"
            print(f"{now.astimezone(IST):%H:%M:%S} OI changed on {n} contracts (gap {gap})")
        prev = cur
        await asyncio.sleep(poll_s)

    s = summarise(changes)
    print(f"\nOI changes seen: {s['changes']}")
    if s["median_s"] is not None:
        print(
            f"gap between changes: min {s['min_s']:.0f}s, "
            f"median {s['median_s']:.0f}s, max {s['max_s']:.0f}s"
        )
        print(f"(measured with a {poll_s}s poll, so each gap is accurate to about ±{poll_s}s)")
    await c.redis.aclose()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--underlying", default="NIFTY")
    ap.add_argument("--minutes", type=int, default=20)
    ap.add_argument("--poll", type=int, default=15, help="seconds between polls (>= 5)")
    a = ap.parse_args()
    asyncio.run(measure(a.underlying, a.minutes, max(5, a.poll)))


if __name__ == "__main__":
    main()
