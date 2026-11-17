"""Resolve provider codes to adapters. The only place that knows concrete classes."""

from __future__ import annotations

from collections.abc import Callable

from providers.base import MarketDataProvider

_FACTORIES: dict[str, Callable[[], MarketDataProvider]] = {}


def register(code: str, factory: Callable[[], MarketDataProvider]) -> None:
    _FACTORIES[code] = factory


def create(code: str) -> MarketDataProvider:
    try:
        return _FACTORIES[code]()
    except KeyError as exc:
        raise ValueError(f"unknown market data provider: {code!r}") from exc


def available() -> list[str]:
    return sorted(_FACTORIES)
