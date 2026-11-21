"""AI views router (no DB): owner-only writes, the caller never supplies a reference price,
and the routes are mounted under /api/v1/ai."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from api.deps import CurrentUser
from api.routers.ai_views import _require_owner, router
from market_data.views.service import RecordViewIn


def test_only_owner_writes() -> None:
    _require_owner(CurrentUser(1, "o@x", ["owner"]))
    with pytest.raises(HTTPException) as exc:
        _require_owner(CurrentUser(2, "v@x", ["viewer"]))
    assert exc.value.status_code == 403


def test_body_never_carries_a_reference_price() -> None:
    base = {"symbol": "NIFTY", "direction": "up", "horizon_days": 5, "confidence": 0.7}
    RecordViewIn.model_validate({**base, "caller": "owner"})
    for extra in ({"ref_price": 1}, {"ref_source": "x"}, {"ref_ts": "2026-01-01T00:00:00Z"}):
        with pytest.raises(ValidationError):
            RecordViewIn.model_validate({**base, "caller": "owner", **extra})


def test_routes() -> None:
    paths = {(m, r.path) for r in router.routes for m in getattr(r, "methods", ())}
    assert {
        ("GET", "/ai/observations"),
        ("POST", "/ai/observations"),
        ("GET", "/ai/accuracy"),
        ("POST", "/ai/views/rebuild"),
    } <= paths
