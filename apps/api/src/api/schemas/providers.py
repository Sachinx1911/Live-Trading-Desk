from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from providers.base import ConnectionState


class ProviderStatus(BaseModel):
    code: str
    display_name: str
    state: ConnectionState
    is_demo: bool
    is_active: bool
    capabilities: list[str]
    latency_ms: float | None = None
    last_message_at: datetime | None = None
    message: str | None = None
    session_valid_until: datetime | None = None


class ProvidersResponse(BaseModel):
    mode: str  # single | comparison | failover
    active: str
    available: list[str]
    providers: list[ProviderStatus]
