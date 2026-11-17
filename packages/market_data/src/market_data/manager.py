"""ProviderManager: single / comparison / controlled-failover modes over MarketDataProvider
adapters. Decides which provider is `active`; never switches back automatically."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from core.calendar import ExchangeCalendar
from core.logging import get_logger
from core.time import utcnow
from providers.base import ConnectionState, MarketDataProvider, ProviderHealth

log = get_logger(__name__)


class ProviderMode(StrEnum):
    SINGLE = "single"
    COMPARISON = "comparison"
    FAILOVER = "failover"


@dataclass(frozen=True)
class SwitchEvent:
    at: datetime
    from_code: str
    to_code: str
    reason: str
    automatic: bool


SwitchCallback = Callable[[SwitchEvent], Awaitable[None]]
Clock = Callable[[], datetime]


class ProviderManager:
    def __init__(
        self,
        primary: MarketDataProvider,
        secondary: MarketDataProvider | None = None,
        *,
        mode: ProviderMode = ProviderMode.SINGLE,
        calendar: ExchangeCalendar | None = None,
        failover_after_s: float = 15.0,
        on_switch: SwitchCallback | None = None,
        clock: Clock = utcnow,
    ) -> None:
        if mode != ProviderMode.SINGLE and secondary is None:
            raise ValueError(f"mode {mode} requires a secondary provider")
        self._providers: dict[str, MarketDataProvider] = {primary.info.code: primary}
        if secondary is not None:
            self._providers[secondary.info.code] = secondary
        self._primary_code = primary.info.code
        self._secondary_code = secondary.info.code if secondary else None
        self._active_code = primary.info.code
        self.mode = mode
        self._cal = calendar
        self._failover_after_s = failover_after_s
        self._on_switch = on_switch
        self._clock = clock
        self._unhealthy_since: datetime | None = None
        self._switched_on: date | None = None
        self.history: list[SwitchEvent] = []

    # ------------------------------------------------------------------ properties
    @property
    def active(self) -> MarketDataProvider:
        return self._providers[self._active_code]

    @property
    def active_code(self) -> str:
        return self._active_code

    @property
    def providers(self) -> dict[str, MarketDataProvider]:
        return dict(self._providers)

    @property
    def comparison_targets(self) -> list[MarketDataProvider]:
        """Providers that should all be streamed when comparing feeds."""
        if self.mode == ProviderMode.COMPARISON:
            return list(self._providers.values())
        return [self.active]

    # ------------------------------------------------------------------ lifecycle
    async def connect_all(self) -> None:
        targets = self._providers.values() if self.mode != ProviderMode.SINGLE else [self.active]
        for p in targets:
            try:
                await p.connect()
            except Exception as exc:
                log.warning("provider.connect_failed", provider=p.info.code, error=str(exc))

    async def disconnect_all(self) -> None:
        for p in self._providers.values():
            try:
                await p.disconnect()
            except Exception as exc:
                log.warning("provider.disconnect_failed", provider=p.info.code, error=str(exc))

    async def health_all(self) -> dict[str, ProviderHealth]:
        return {code: await p.health() for code, p in self._providers.items()}

    # ------------------------------------------------------------------ switching
    async def switch_to(
        self, code: str, reason: str, *, automatic: bool = False
    ) -> SwitchEvent | None:
        if code not in self._providers:
            raise ValueError(f"unknown provider {code!r}")
        if code == self._active_code:
            return None
        ev = SwitchEvent(
            at=self._clock(),
            from_code=self._active_code,
            to_code=code,
            reason=reason,
            automatic=automatic,
        )
        self._active_code = code
        self._unhealthy_since = None
        self.history.append(ev)
        log.warning("provider.switched", **ev.__dict__)
        if self._on_switch is not None:
            await self._on_switch(ev)
        return ev

    async def check(self) -> SwitchEvent | None:
        """Evaluate the failover rule once. Call periodically (e.g. every few seconds).

        Rule: in FAILOVER mode, while the market is open, if the active (primary) provider is
        not CONNECTED for `failover_after_s` and the secondary is CONNECTED, promote the
        secondary. One automatic switch per session day; never auto-switch back.
        """
        if self.mode != ProviderMode.FAILOVER or self._secondary_code is None:
            return None
        if self._active_code != self._primary_code:
            return None  # already failed over; manual switch_to() required to return
        now = self._clock()
        if self._cal is not None and not self._cal.is_open(now):
            self._unhealthy_since = None
            return None
        if self._switched_on == (self._cal.local_date(now) if self._cal else now.date()):
            return None
        primary_h = await self._providers[self._primary_code].health()
        if primary_h.state == ConnectionState.CONNECTED:
            self._unhealthy_since = None
            return None
        if self._unhealthy_since is None:
            self._unhealthy_since = now
            return None
        if (now - self._unhealthy_since).total_seconds() < self._failover_after_s:
            return None
        secondary_h = await self._providers[self._secondary_code].health()
        if secondary_h.state != ConnectionState.CONNECTED:
            return None
        self._switched_on = self._cal.local_date(now) if self._cal else now.date()
        reason = (
            f"primary {self._primary_code} {primary_h.state.value} "
            f"for >= {self._failover_after_s:.0f}s"
        )
        return await self.switch_to(self._secondary_code, reason=reason, automatic=True)
