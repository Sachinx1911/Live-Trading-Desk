from __future__ import annotations


class UpstoxError(Exception):
    """Base class for Upstox adapter errors."""

    def __init__(self, message: str, *, status: int | None = None, code: str | None = None):
        super().__init__(message)
        self.status = status
        self.code = code


class UpstoxAuthError(UpstoxError):
    """401 / missing or expired token: user must log in again (ADR-012)."""


class UpstoxRateLimitError(UpstoxError):
    """429 from the API."""
