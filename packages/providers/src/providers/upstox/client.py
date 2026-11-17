"""Thin async REST client: bearer auth, rate limiting, retries, structured errors."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from providers.upstox.errors import UpstoxAuthError, UpstoxError, UpstoxRateLimitError
from providers.upstox.ratelimit import MultiWindowRateLimiter

API_BASE = "https://api.upstox.com"


class _RetryableError(UpstoxError):
    pass


class UpstoxRest:
    def __init__(
        self,
        token_getter: Callable[[], str | None],
        *,
        base_url: str = API_BASE,
        limiter: MultiWindowRateLimiter | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 20.0,
        max_attempts: int = 3,
    ) -> None:
        self._token_getter = token_getter
        self._base = base_url.rstrip("/")
        self._limiter = limiter or MultiWindowRateLimiter()
        self._client = httpx.AsyncClient(transport=transport, timeout=timeout)
        self._max_attempts = max_attempts

    async def aclose(self) -> None:
        await self._client.aclose()

    def _headers(self) -> dict[str, str]:
        token = self._token_getter()
        if not token:
            raise UpstoxAuthError("no Upstox access token; daily login required")
        return {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    async def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """GET `path` (relative to base or absolute) and return parsed JSON `data`-less body."""
        url = path if path.startswith("http") else f"{self._base}{path}"
        headers = self._headers()
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self._max_attempts),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
            retry=retry_if_exception_type(_RetryableError),
            reraise=True,
        ):
            with attempt:
                await self._limiter.acquire()
                try:
                    resp = await self._client.get(url, params=params, headers=headers)
                except httpx.TransportError as exc:
                    raise _RetryableError(f"transport error: {exc}") from exc
                return self._handle(resp)
        raise UpstoxError("unreachable")  # pragma: no cover

    @staticmethod
    def _handle(resp: httpx.Response) -> Any:
        if resp.status_code == 401:
            raise UpstoxAuthError("Upstox rejected the token (401)", status=401)
        if resp.status_code == 429:
            raise _RetryableError("rate limited (429)", status=429)
        if resp.status_code >= 500:
            raise _RetryableError(f"server error {resp.status_code}", status=resp.status_code)
        if resp.status_code >= 400:
            code = None
            try:
                errs = resp.json().get("errors") or []
                code = errs[0].get("errorCode") if errs else None
            except Exception:  # noqa: S110 - best-effort error code extraction
                pass
            raise UpstoxError(
                f"Upstox error {resp.status_code}: {resp.text[:300]}",
                status=resp.status_code,
                code=code,
            )
        body = resp.json()
        if isinstance(body, dict) and body.get("status") not in (None, "success"):
            raise UpstoxError(f"Upstox status={body.get('status')}: {str(body)[:300]}")
        return body


def rate_limit_error_from(exc: _RetryableError) -> UpstoxRateLimitError:
    return UpstoxRateLimitError(str(exc), status=exc.status)
