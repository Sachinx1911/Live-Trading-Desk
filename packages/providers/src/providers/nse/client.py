"""Polite async client for NSE's public endpoints.

NSE blocks requests that do not look like a browser and requires cookies obtained from a
prior visit to the home page. We bootstrap cookies once per client, send a browser-like
User-Agent, rate-limit to one request per second and retry with backoff on transient
failures. Nothing here authenticates: these are public files and JSON endpoints.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, date, datetime
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from core.logging import get_logger
from core.time import IST

log = get_logger(__name__)

NSE_HOME = "https://www.nseindia.com"
NSE_API = "https://www.nseindia.com/api"
NSE_ARCHIVES = "https://nsearchives.nseindia.com"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}


class NseError(Exception):
    pass


class NseTransientError(NseError):
    """5xx / 403 (cookie expiry) / network error; retried."""


class NseClient:
    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 30.0,
        min_interval_s: float = 1.0,
    ) -> None:
        self._client = httpx.AsyncClient(
            headers=_HEADERS, timeout=timeout, transport=transport, follow_redirects=True
        )
        self._min_interval = min_interval_s
        self._last_request = 0.0
        self._cookies_ready = False
        self._lock = asyncio.Lock()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> NseClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    # -- plumbing ------------------------------------------------------------------
    async def _throttle(self) -> None:
        async with self._lock:
            wait = self._min_interval - (time.monotonic() - self._last_request)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request = time.monotonic()

    async def _bootstrap_cookies(self) -> None:
        if self._cookies_ready:
            return
        await self._throttle()
        try:
            r = await self._client.get(NSE_HOME)
            r.raise_for_status()
        except httpx.HTTPError as exc:
            raise NseTransientError(f"cookie bootstrap failed: {exc}") from exc
        self._cookies_ready = True

    @retry(
        retry=retry_if_exception_type(NseTransientError),
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=1, max=20),
        reraise=True,
    )
    async def _get(
        self, url: str, *, needs_cookies: bool, params: dict[str, str] | None = None
    ) -> httpx.Response:
        if needs_cookies:
            await self._bootstrap_cookies()
        await self._throttle()
        try:
            r = await self._client.get(url, params=params)
        except httpx.HTTPError as exc:
            raise NseTransientError(f"request failed: {exc}") from exc
        if r.status_code in (401, 403):
            # NSE invalidates cookies periodically; refresh on the next attempt.
            self._cookies_ready = False
            raise NseTransientError(f"nse rejected request ({r.status_code}) for {url}")
        if r.status_code >= 500:
            raise NseTransientError(f"nse server error {r.status_code} for {url}")
        if r.status_code == 404:
            raise NseError(f"not found: {url}")
        if r.status_code >= 400:
            raise NseError(f"nse error {r.status_code} for {url}")
        return r

    # -- endpoints -------------------------------------------------------------------
    async def fetch_holidays(self, year: int | None = None) -> dict[str, Any]:
        """Raw holiday-master JSON (keys CM, FO, ...). NSE serves the current year only;
        `year` is accepted for interface symmetry and logged if it is not the current year."""
        r = await self._get(
            f"{NSE_API}/holiday-master", needs_cookies=True, params={"type": "trading"}
        )
        try:
            data = r.json()
        except ValueError as exc:
            raise NseError("holiday-master returned non-JSON") from exc
        if not isinstance(data, dict):
            raise NseError("holiday-master JSON is not an object")
        if year is not None and year != datetime.now(tz=UTC).astimezone(IST).year:
            log.warning("nse.holidays.year_not_served", requested=year)
        return data

    @staticmethod
    def cm_bhavcopy_url(d: date) -> str:
        return f"{NSE_ARCHIVES}/content/cm/BhavCopy_NSE_CM_0_0_0_{d:%Y%m%d}_F_0000.csv.zip"

    @staticmethod
    def fo_bhavcopy_url(d: date) -> str:
        return f"{NSE_ARCHIVES}/content/fo/BhavCopy_NSE_FO_0_0_0_{d:%Y%m%d}_F_0000.csv.zip"

    async def fetch_cm_bhavcopy(self, d: date) -> bytes:
        r = await self._get(self.cm_bhavcopy_url(d), needs_cookies=False)
        return r.content

    async def fetch_fo_bhavcopy(self, d: date) -> bytes:
        r = await self._get(self.fo_bhavcopy_url(d), needs_cookies=False)
        return r.content

    async def fetch_corporate_actions(self, start: date, end: date) -> list[dict[str, Any]]:
        r = await self._get(
            f"{NSE_API}/corporates-corporate-actions",
            needs_cookies=True,
            params={
                "index": "equities",
                "from_date": f"{start:%d-%m-%Y}",
                "to_date": f"{end:%d-%m-%Y}",
            },
        )
        try:
            data = r.json()
        except ValueError as exc:
            raise NseError("corporate-actions returned non-JSON") from exc
        if not isinstance(data, list):
            raise NseError("corporate-actions JSON is not a list")
        return [row for row in data if isinstance(row, dict)]
