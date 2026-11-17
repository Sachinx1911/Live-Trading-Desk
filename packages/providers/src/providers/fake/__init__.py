"""Deterministic demo provider. Everything it emits is flagged is_demo=True (CLAUDE.md rule 5)."""

from providers.fake.provider import FakeMarketDataProvider


def register() -> None:
    from providers import registry

    registry.register("fake", lambda: FakeMarketDataProvider())


__all__ = ["FakeMarketDataProvider", "register"]
