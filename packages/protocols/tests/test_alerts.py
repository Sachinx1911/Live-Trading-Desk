"""Alert rules (pure) and the dedup window."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from itertools import pairwise

from hypothesis import given, settings
from hypothesis import strategies as st

from protocols.alerts import (
    AlertCandidate,
    AlertFacts,
    AlertParams,
    BrokerFact,
    FeedFact,
    KillFact,
    PaperLossFact,
    PcrFact,
    TraderFact,
    broker_session,
    daily_loss_near,
    dedup,
    evaluate,
    feed_stale,
    kill_switch_active,
    pcr_near_limit,
    trader_down,
)

NOW = datetime(2026, 11, 23, 5, 0, tzinfo=UTC)  # Monday 10:30 IST
P = AlertParams()


def _facts(**kw: object) -> AlertFacts:
    base: dict[str, object] = {"now": NOW, "market_open": True}
    base.update(kw)
    return AlertFacts(**base)  # type: ignore[arg-type]


def _pcr(v: str, age_min: int = 2) -> PcrFact:
    return PcrFact("NIFTY", 1, Decimal(v), NOW - timedelta(minutes=age_min), "2026-11-25")


# ---------------------------------------------------------------- pcr_near_limit
def test_pcr_neutral_no_alert() -> None:
    assert pcr_near_limit(_facts(pcr=(_pcr("1.0"),)), P) == []


def test_pcr_near_and_beyond_put_limit() -> None:
    near = pcr_near_limit(_facts(pcr=(_pcr("1.92"),)), P)
    assert [(a.severity, a.dedup_key) for a in near] == [("info", "pcr_near_limit:NIFTY:put:near")]
    assert near[0].data["pcr"] == "1.92" and near[0].instrument_id == 1
    beyond = pcr_near_limit(_facts(pcr=(_pcr("2.00"),)), P)
    assert [(a.severity, a.dedup_key) for a in beyond] == [
        ("warning", "pcr_near_limit:NIFTY:put:beyond")
    ]


def test_pcr_near_and_beyond_call_limit() -> None:
    assert pcr_near_limit(_facts(pcr=(_pcr("0.58"),)), P)[0].dedup_key.endswith("call:near")
    assert pcr_near_limit(_facts(pcr=(_pcr("0.5"),)), P)[0].dedup_key.endswith("call:beyond")
    assert pcr_near_limit(_facts(pcr=(_pcr("0.61"),)), P) == []


def test_pcr_margin_setting_is_used() -> None:
    wide = AlertParams(pcr_margin=Decimal("0.5"))
    assert pcr_near_limit(_facts(pcr=(_pcr("1.6"),)), wide)
    assert not pcr_near_limit(_facts(pcr=(_pcr("1.6"),)), P)


def test_pcr_stale_or_missing_is_not_judged() -> None:
    assert pcr_near_limit(_facts(pcr=(_pcr("2.5", age_min=30),)), P) == []
    assert pcr_near_limit(_facts(pcr=(PcrFact("NIFTY", 1, None, None),)), P) == []


@given(st.decimals(min_value=Decimal("0.01"), max_value=Decimal("5"), places=2))
def test_pcr_alert_iff_within_margin_or_beyond(v: Decimal) -> None:
    out = pcr_near_limit(_facts(pcr=(_pcr(str(v)),)), P)
    expect = v >= Decimal("1.9") or v <= Decimal("0.6")
    assert bool(out) == expect


# ---------------------------------------------------------------- feed_stale
def test_feed_ok_no_alert() -> None:
    f = FeedFact(True, "connected", NOW - timedelta(seconds=5), "upstox")
    assert feed_stale(_facts(feed=f), P) == []


def test_feed_missing_down_and_silent() -> None:
    assert feed_stale(_facts(feed=FeedFact(False)), P)[0].dedup_key == "feed_stale:missing"
    down = feed_stale(_facts(feed=FeedFact(True, "reconnecting", NOW, "upstox")), P)
    assert down[0].severity == "critical" and down[0].dedup_key == "feed_stale:state:reconnecting"
    silent = FeedFact(True, "connected", NOW - timedelta(seconds=121), "upstox")
    out = feed_stale(_facts(feed=silent), P)
    assert out[0].dedup_key == "feed_stale:silent" and out[0].data["last_message_age_s"] == 121


def test_feed_ignored_outside_market_hours() -> None:
    assert feed_stale(_facts(market_open=False, feed=FeedFact(False)), P) == []


# ---------------------------------------------------------------- broker_session
def test_broker_session_rules() -> None:
    f = _facts(
        brokers=(
            BrokerFact("upstox", "valid", NOW + timedelta(hours=5)),
            BrokerFact("dhan", "expired", NOW - timedelta(hours=1)),
        )
    )
    out = broker_session(f, P)
    assert [(a.severity, a.dedup_key) for a in out] == [("critical", "broker_session:dhan:expired")]
    soon = broker_session(
        _facts(brokers=(BrokerFact("upstox", "valid", NOW + timedelta(minutes=20)),)), P
    )
    assert soon[0].dedup_key == "broker_session:upstox:expiring" and "20 min" in soon[0].title


# ---------------------------------------------------------------- daily_loss_near
def _acct(realized: str) -> PaperLossFact:
    return PaperLossFact(7, "Paper", Decimal(realized), Decimal("100000"), 2.0)  # cap 2000


def test_daily_loss_thresholds() -> None:
    assert daily_loss_near(_facts(paper=(_acct("-1499"),)), P) == []
    near = daily_loss_near(_facts(paper=(_acct("-1500"),)), P)
    assert near[0].severity == "warning" and near[0].dedup_key == "daily_loss_near:7:near"
    hit = daily_loss_near(_facts(paper=(_acct("-2100"),)), P)
    assert hit[0].severity == "critical" and hit[0].dedup_key == "daily_loss_near:7:hit"
    assert daily_loss_near(_facts(paper=(_acct("500"),)), P) == []


# ---------------------------------------------------------------- kill / trader
def test_kill_switch_active() -> None:
    out = kill_switch_active(_facts(kill=(KillFact("global", "clean slate", "protocol"),)), P)
    assert out[0].dedup_key == "kill_switch_active:global" and "clean slate" in out[0].message


def test_trader_down() -> None:
    fresh = TraderFact(True, NOW - timedelta(seconds=60), 2)
    assert trader_down(_facts(trader=fresh), P) == []
    old = trader_down(_facts(trader=TraderFact(True, NOW - timedelta(seconds=200), 2)), P)
    assert old[0].severity == "critical" and old[0].data["age_s"] == 200
    missing = trader_down(_facts(trader=TraderFact(False, None, 0)), P)
    assert missing[0].severity == "warning"
    assert trader_down(_facts(market_open=False, trader=TraderFact(False)), P) == []


def test_evaluate_runs_every_rule() -> None:
    f = _facts(
        pcr=(_pcr("2.2"),),
        feed=FeedFact(False),
        brokers=(BrokerFact("upstox", "revoked"),),
        paper=(_acct("-1800"),),
        trader=TraderFact(False),
        kill=(KillFact("global", "x"),),
    )
    kinds = {a.kind for a in evaluate(f, P)}
    assert kinds == {
        "pcr_near_limit",
        "feed_stale",
        "broker_session",
        "daily_loss_near",
        "kill_switch_active",
        "trader_down",
    }


# ---------------------------------------------------------------- dedup
def _c(key: str) -> AlertCandidate:
    return AlertCandidate("k", "info", "t", "m", key)


def test_dedup_window() -> None:
    w = timedelta(minutes=30)
    seen: dict[str, datetime] = {}
    assert len(dedup([_c("a"), _c("a"), _c("b")], seen, NOW, w)) == 2
    assert dedup([_c("a")], seen, NOW + timedelta(minutes=29), w) == []
    assert len(dedup([_c("a")], seen, NOW + timedelta(minutes=30), w)) == 1


@settings(max_examples=200)
@given(
    st.lists(
        st.tuples(st.integers(min_value=0, max_value=600), st.sampled_from(["a", "b", "c"])),
        max_size=60,
    ),
    st.integers(min_value=1, max_value=120),
)
def test_dedup_never_stores_same_key_twice_inside_window(
    events: list[tuple[int, str]], window_min: int
) -> None:
    """Feed evaluations in time order; stored alerts with the same key are always at least
    one window apart, and a key absent for a full window is always stored again."""
    window = timedelta(minutes=window_min)
    seen: dict[str, datetime] = {}
    stored: list[tuple[datetime, str]] = []
    for minute, key in sorted(events):
        now = NOW + timedelta(minutes=minute)
        prev = max((t for t, k in stored if k == key), default=None)
        out = dedup([_c(key), _c(key)], seen, now, window)
        assert len(out) <= 1
        if prev is None or now - prev >= window:
            assert len(out) == 1
        stored.extend((now, c.dedup_key) for c in out)
    by_key: dict[str, list[datetime]] = {}
    for t, k in stored:
        by_key.setdefault(k, []).append(t)
    for ts in by_key.values():
        assert all(b - a >= window for a, b in pairwise(ts))
