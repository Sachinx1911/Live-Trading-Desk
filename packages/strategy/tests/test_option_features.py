"""DSL 1.1 `option` operand: schema rules, values, opening baseline, no look-ahead, validator."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from strategy.dsl.schema import OptionRef, StrategyDocument
from strategy.dsl.validate import validate_document
from strategy.option_features import (
    ChainHistory,
    document_uses_options,
    option_value,
    view_from_rows,
)

T0 = datetime(2026, 11, 17, 3, 45, tzinfo=UTC)  # 09:15 IST


def _rows(ce: int, pe: int) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for i, k in enumerate((24900, 25000, 25100)):
        out.append({"strike": k, "option_type": "CE", "oi": ce + i, "iv": 12 + i, "delta": 0.5})
        out.append({"strike": k, "option_type": "PE", "oi": pe + i, "iv": 14 + i, "delta": -0.5})
    return out


def ref(**kw: object) -> OptionRef:
    return OptionRef.model_validate({"kind": "option", **kw})


def test_schema_rules() -> None:
    ref(feature="pcr")
    ref(feature="greek", side="CE", greek="delta", strike_offset=-2)
    for bad in (
        {"feature": "oi"},  # no side
        {"feature": "greek", "side": "CE"},  # no greek
        {"feature": "pcr", "side": "PE"},
        {"feature": "oi", "side": "CE", "greek": "delta"},
        {"feature": "oi", "side": "CE", "strike_offset": 11},
    ):
        with pytest.raises(ValidationError):
            ref(**bad)


def test_values_on_one_view() -> None:
    v = view_from_rows(T0, 25010, _rows(1000, 1500))
    pcr = option_value(ref(feature="pcr"), v)
    assert pcr == pytest.approx((1500 + 1501 + 1502) / (1000 + 1001 + 1002))
    assert option_value(ref(feature="iv_atm"), v) == pytest.approx((13 + 15) / 2)  # ATM 25000
    assert option_value(ref(feature="oi", side="PE", strike_offset=1), v) == 1502
    assert option_value(ref(feature="greek", side="CE", greek="delta"), v) == 0.5
    assert option_value(ref(feature="oi", side="CE", strike_offset=3), v) is None  # off chain
    assert option_value(ref(feature="oi_change_from_open", side="CE"), v) is None  # no baseline
    assert option_value(ref(feature="pcr"), None) is None
    no_spot = view_from_rows(T0, None, _rows(1, 1))
    assert option_value(ref(feature="oi", side="CE"), no_spot) is None


def test_history_opening_baseline_and_before_open() -> None:
    h = ChainHistory.from_snapshots(
        [
            (T0 - timedelta(minutes=15), 25000, _rows(500, 500)),  # 09:00 IST, before the open
            (T0, 25000, _rows(1000, 400)),  # the opening snapshot
            (T0 + timedelta(minutes=3), 25000, _rows(1300, 350)),
        ]
    )
    change = ref(feature="oi_change_from_open", side="CE")
    assert option_value(change, h.at(T0 - timedelta(minutes=10))) is None
    assert option_value(change, h.at(T0)) == 0
    assert option_value(change, h.at(T0 + timedelta(minutes=4))) == 300
    assert (
        option_value(ref(feature="oi_change_from_open", side="PE"), h.at(T0 + timedelta(minutes=4)))
        == -50
    )
    assert h.at(T0 - timedelta(hours=1)) is None


@given(
    st.lists(st.integers(min_value=0, max_value=5000), max_size=40),
    st.integers(min_value=-60, max_value=5100),
)
def test_history_never_looks_ahead(offsets: list[int], probe: int) -> None:
    h = ChainHistory.from_snapshots(
        (T0 + timedelta(seconds=o), 25000, _rows(o, o)) for o in set(offsets)
    )
    now = T0 + timedelta(seconds=probe)
    v = h.at(now)
    visible = [T0 + timedelta(seconds=o) for o in set(offsets) if T0 + timedelta(seconds=o) <= now]
    if not visible:
        assert v is None
    else:
        assert v is not None and v.ts == max(visible) and v.ts <= now


def _doc(version: str) -> StrategyDocument:
    return StrategyDocument.model_validate(
        {
            "dsl_schema_version": version,
            "name": "pcr filter",
            "origin": "user_visual",
            "market": "NSE",
            "universe": {"kind": "instrument", "instrument_ids": ["1"]},
            "timeframe": "5m",
            "session": {"product": "INTRADAY"},
            "direction": "long_only",
            "entry": {
                "long": {
                    "kind": "compare",
                    "left": {"kind": "option", "feature": "pcr"},
                    "op": "lt",
                    "right": {"kind": "const", "value": 1},
                }
            },
            "exit": {"time_exit_bars": 2},
        }
    )


def test_validator_needs_1_1_and_warns_about_history() -> None:
    old = validate_document(_doc("1.0"))
    assert any("dsl_schema_version 1.1" in e for e in old.errors)
    new = validate_document(_doc("1.1"))
    assert not any("1.1" in e for e in new.errors)
    assert any("option-chain data" in w for w in new.warnings)
    assert document_uses_options(_doc("1.1"))
