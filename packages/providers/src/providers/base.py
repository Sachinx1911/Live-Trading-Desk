"""Provider interfaces. Every adapter (fake, upstox, dhan, ...) implements these and maps
its payloads to the canonical models in `core.models`. Nothing outside
`packages/providers` may import a concrete adapter; use `providers.registry`."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from core.models import Candle, Instrument, OptionChainSnapshot, Quote, Tick, Timeframe


class ProviderCapability(StrEnum):
    LIVE_QUOTES = "live_quotes"
    LIVE_TICKS = "live_ticks"
    MARKET_DEPTH = "market_depth"
    HISTORICAL_CANDLES = "historical_candles"
    OPTION_CHAIN = "option_chain"
    INSTRUMENT_MASTER = "instrument_master"
    ORDERS = "orders"


class ConnectionState(StrEnum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    AUTH_REQUIRED = "auth_required"  # token expired; user must log in (ADR-012)
    ERROR = "error"


@dataclass(frozen=True)
class ProviderInfo:
    code: str  # "fake" | "upstox" | "dhan"
    display_name: str
    capabilities: frozenset[ProviderCapability]
    is_demo: bool = False
    supported_timeframes: frozenset[Timeframe] = field(default_factory=frozenset)


@dataclass
class ProviderHealth:
    code: str
    state: ConnectionState
    last_message_at: datetime | None = None
    latency_ms: float | None = None
    reconnects_today: int = 0
    message: str | None = None
    session_valid_until: datetime | None = None


class MarketDataProvider(ABC):
    """Read-only market data. Implementations must be safe to run alongside another
    provider (comparison mode) and must never block the event loop."""

    @property
    @abstractmethod
    def info(self) -> ProviderInfo: ...

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def health(self) -> ProviderHealth: ...

    @abstractmethod
    async def fetch_instruments(self) -> Sequence[Instrument]:
        """Full instrument master as canonical instruments (ids may be provisional; the
        market_data package reconciles them against the DB)."""

    @abstractmethod
    async def get_quotes(self, instrument_ids: Sequence[int]) -> Sequence[Quote]: ...

    @abstractmethod
    async def get_candles(
        self,
        instrument_id: int,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> Sequence[Candle]: ...

    @abstractmethod
    async def get_option_chain(
        self, underlying_instrument_id: int, expiry: datetime
    ) -> OptionChainSnapshot: ...

    @abstractmethod
    def stream_ticks(self, instrument_ids: Sequence[int]) -> AsyncIterator[Tick]:
        """Async iterator of canonical ticks. Must handle reconnects internally and
        reflect them in `health()`."""


class BrokerAdapter(ABC):
    """Order routing. Implemented in Phase 3+. Only `execution.live.gateway` may call it."""

    @property
    @abstractmethod
    def code(self) -> str: ...

    @abstractmethod
    async def session_status(self) -> ProviderHealth: ...

    @abstractmethod
    def login_url(self, state: str) -> str: ...

    @abstractmethod
    async def complete_login(self, code: str) -> datetime:
        """Exchange the OAuth code for a token; return its expiry (UTC)."""
