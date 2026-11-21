"""Protocol router validation (no DB): owner-defined protocols are checked against the
action registry before anything is stored."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from api.deps import CurrentUser
from api.routers.protocols import ProtocolBody, _require_owner, _spec


def _body(steps: list[dict[str, object]], confirm: bool = False) -> ProtocolBody:
    return ProtocolBody(name="Mine", steps=steps, confirm_required=confirm)


def test_valid_owner_protocol() -> None:
    spec = _spec("my_check", _body([{"tool": "health_check"}, {"tool": "pcr_now"}]))
    assert [s.tool for s in spec.steps] == ["health_check", "pcr_now"]
    assert spec.steps[0].on_error == "stop"


@pytest.mark.parametrize(
    ("code", "steps", "needle"),
    [
        ("my_check", [{"tool": "place_order"}], "unknown action"),
        ("my_check", [{"tool": "recent_alerts", "args": {"hours": 0}}], "hours"),
        ("my_check", [{"tool": "health_check", "exec": "rm -rf /"}], "exec"),
        ("Bad-Code", [{"tool": "health_check"}], "code"),
        ("runs", [{"tool": "health_check"}], "reserved"),
    ],
)
def test_invalid_protocols_rejected(code: str, steps: list[dict[str, object]], needle: str) -> None:
    with pytest.raises(HTTPException) as exc:
        _spec(code, _body(steps))
    assert exc.value.status_code == 422
    assert needle in str(exc.value.detail)


def test_only_owner_edits() -> None:
    _require_owner(CurrentUser(1, "o@x", ["owner"]))
    with pytest.raises(HTTPException) as exc:
        _require_owner(CurrentUser(2, "v@x", ["viewer"]))
    assert exc.value.status_code == 403
