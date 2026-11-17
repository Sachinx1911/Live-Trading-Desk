from __future__ import annotations

from fastapi import APIRouter

from api.deps import State, User
from api.schemas.providers import ProvidersResponse, ProviderStatus
from providers import registry
from providers.base import ConnectionState

router = APIRouter(prefix="/providers", tags=["providers"])

DISPLAY = {"fake": "Demo provider", "upstox": "Upstox", "dhan": "Dhan"}


@router.get("", response_model=ProvidersResponse)
async def list_providers(state: State, _: User) -> ProvidersResponse:
    """Status of every known provider. Only the active one is connected in Phase 1."""
    active = state.provider.info.code
    h = await state.provider.health()
    rows = [
        ProviderStatus(
            code=active,
            display_name=state.provider.info.display_name,
            state=h.state,
            is_demo=state.provider.info.is_demo,
            is_active=True,
            capabilities=sorted(c.value for c in state.provider.info.capabilities),
            latency_ms=h.latency_ms,
            last_message_at=h.last_message_at,
            message=h.message,
            session_valid_until=h.session_valid_until,
        )
    ]
    for code in ("upstox", "dhan"):
        if code != active:
            rows.append(
                ProviderStatus(
                    code=code,
                    display_name=DISPLAY[code],
                    state=ConnectionState.DISCONNECTED,
                    is_demo=False,
                    is_active=False,
                    capabilities=[],
                    message="not configured (ships in Phase 2/7)",
                )
            )
    return ProvidersResponse(
        mode="single", active=active, available=registry.available(), providers=rows
    )
