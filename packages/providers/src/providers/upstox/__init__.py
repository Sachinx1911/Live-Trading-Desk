"""Upstox adapter. Only this package knows Upstox payload shapes and endpoints."""

from providers.upstox.provider import UpstoxMarketDataProvider, register

__all__ = ["UpstoxMarketDataProvider", "register"]
