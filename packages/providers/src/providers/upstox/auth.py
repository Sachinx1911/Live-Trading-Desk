"""Upstox OAuth: build the login URL and exchange the one-time code for a token.

Tokens are stored elsewhere (encrypted, broker_sessions). This module never persists.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx

from core.time import IST, ensure_utc, utcnow
from providers.upstox.errors import UpstoxAuthError, UpstoxError

API_BASE = "https://api.upstox.com"
TOKEN_EXPIRY_LOCAL = time(3, 30)  # tokens die at ~03:30 IST the next day


def token_expiry_after(issued_at: datetime) -> datetime:
    """03:30 IST on the calendar day after issuance (in IST), as UTC."""
    local = ensure_utc(issued_at).astimezone(IST)
    next_day = (local + timedelta(days=1)).date()
    return datetime.combine(next_day, TOKEN_EXPIRY_LOCAL, tzinfo=IST).astimezone(
        ensure_utc(issued_at).tzinfo
    )


class UpstoxAuth:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        *,
        base_url: str = API_BASE,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._base = base_url.rstrip("/")
        self._transport = transport

    def login_url(self, state: str) -> str:
        q = urlencode(
            {
                "response_type": "code",
                "client_id": self._client_id,
                "redirect_uri": self._redirect_uri,
                "state": state,
            }
        )
        return f"{self._base}/v2/login/authorization/dialog?{q}"

    async def exchange_code(self, code: str) -> tuple[str, datetime]:
        """Return (access_token, expires_at_utc)."""
        form = {
            "code": code,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "redirect_uri": self._redirect_uri,
            "grant_type": "authorization_code",
        }
        async with httpx.AsyncClient(transport=self._transport, timeout=20.0) as client:
            resp = await client.post(
                f"{self._base}/v2/login/authorization/token",
                data=form,
                headers={"accept": "application/json"},
            )
        if resp.status_code in (400, 401):
            raise UpstoxAuthError(
                f"token exchange rejected: {resp.text[:200]}", status=resp.status_code
            )
        if resp.status_code != 200:
            raise UpstoxError(f"token exchange failed: {resp.status_code}", status=resp.status_code)
        body: dict[str, Any] = resp.json()
        token = body.get("access_token")
        if not isinstance(token, str) or not token:
            raise UpstoxAuthError("token exchange response has no access_token")
        return token, token_expiry_after(utcnow())
