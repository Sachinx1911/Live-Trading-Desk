"""NseClient against a MockTransport: cookie bootstrap, retries, throttling. No network."""

from __future__ import annotations

from datetime import date

import httpx
import pytest

from providers.nse.client import NSE_API, NSE_HOME, NseClient, NseError


class _Recorder:
    def __init__(self, responses: dict[str, list[httpx.Response]]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url).split("?")[0]
        self.calls.append(url)
        queue = self.responses.get(url)
        if not queue:
            return httpx.Response(404)
        return queue.pop(0) if len(queue) > 1 else queue[0]


@pytest.fixture
def client_factory():
    def make(responses: dict[str, list[httpx.Response]]) -> tuple[NseClient, _Recorder]:
        rec = _Recorder(responses)
        client = NseClient(transport=httpx.MockTransport(rec.handler), min_interval_s=0)
        return client, rec

    return make


async def test_holidays_bootstraps_cookies_once(client_factory) -> None:
    client, rec = client_factory(
        {
            NSE_HOME: [httpx.Response(200, text="<html/>")],
            f"{NSE_API}/holiday-master": [httpx.Response(200, json={"CM": []})],
        }
    )
    async with client:
        assert await client.fetch_holidays() == {"CM": []}
        assert await client.fetch_holidays() == {"CM": []}
    assert rec.calls.count(NSE_HOME) == 1
    assert rec.calls.count(f"{NSE_API}/holiday-master") == 2


async def test_403_refreshes_cookies_and_retries(client_factory) -> None:
    client, rec = client_factory(
        {
            NSE_HOME: [httpx.Response(200, text="<html/>")],
            f"{NSE_API}/corporates-corporate-actions": [
                httpx.Response(403),
                httpx.Response(200, json=[{"symbol": "X"}, "junk"]),
            ],
        }
    )
    async with client:
        rows = await client.fetch_corporate_actions(date(2026, 10, 1), date(2026, 11, 1))
    assert rows == [{"symbol": "X"}]
    assert rec.calls.count(NSE_HOME) == 2  # re-bootstrapped after the 403


async def test_bhavcopy_404_is_not_retried(client_factory) -> None:
    client, rec = client_factory({})
    async with client:
        with pytest.raises(NseError):
            await client.fetch_fo_bhavcopy(date(2026, 11, 15))  # a Sunday: no file
    assert len(rec.calls) == 1


async def test_bhavcopy_urls() -> None:
    d = date(2026, 11, 14)
    assert NseClient.cm_bhavcopy_url(d).endswith(
        "/cm/BhavCopy_NSE_CM_0_0_0_20261114_F_0000.csv.zip"
    )
    assert NseClient.fo_bhavcopy_url(d).endswith(
        "/fo/BhavCopy_NSE_FO_0_0_0_20261114_F_0000.csv.zip"
    )


async def test_non_json_holidays_raises(client_factory) -> None:
    client, _ = client_factory(
        {
            NSE_HOME: [httpx.Response(200, text="<html/>")],
            f"{NSE_API}/holiday-master": [httpx.Response(200, text="<html>blocked</html>")],
        }
    )
    async with client:
        with pytest.raises(NseError):
            await client.fetch_holidays()
