"""Upstox order API client. PRIVATE: imported only by `execution.live.gateway` callers
through the `BrokerOrderClient` protocol; never by strategy, AI, or API routers directly.
State after submission comes from broker callbacks / reconciliation, not from here."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import Any

import httpx

from core.models import OrderIntent, OrderType, ProductType

API_BASE = "https://api.upstox.com"

_ORDER_TYPE = {
    OrderType.MARKET: "MARKET",
    OrderType.LIMIT: "LIMIT",
    OrderType.STOP: "SL-M",
    OrderType.STOP_LIMIT: "SL",
}
_PRODUCT = {ProductType.INTRADAY: "I", ProductType.DELIVERY: "D", ProductType.CARRY: "D"}


class UpstoxOrderError(Exception):
    pass


class UpstoxOrderClient:
    def __init__(
        self,
        access_token_getter: Callable[[], str | None],
        instrument_key_of: Callable[[int], str],
        *,
        base_url: str = API_BASE,
        transport: httpx.AsyncBaseTransport | None = None,
        tag: str = "trading-platform",
    ) -> None:
        self._token = access_token_getter
        self._key_of = instrument_key_of
        self._base = base_url.rstrip("/")
        self._transport = transport
        self._tag = tag

    def _headers(self) -> dict[str, str]:
        tok = self._token()
        if not tok:
            raise UpstoxOrderError("no valid Upstox session")
        return {"Authorization": f"Bearer {tok}", "Accept": "application/json"}

    def payload(self, intent: OrderIntent) -> dict[str, Any]:
        return {
            "quantity": intent.quantity,
            "product": _PRODUCT[intent.product],
            "validity": "DAY",
            "price": float(intent.limit_price or Decimal(0)),
            "tag": self._tag,
            "instrument_token": self._key_of(intent.instrument_id),
            "order_type": _ORDER_TYPE[intent.order_type],
            "transaction_type": intent.side.value.upper(),
            "disclosed_quantity": 0,
            "trigger_price": float(intent.trigger_price or Decimal(0)),
            "is_amo": False,
        }

    async def place(self, intent: OrderIntent) -> str:
        async with httpx.AsyncClient(
            base_url=self._base, transport=self._transport, timeout=10
        ) as c:
            r = await c.post("/v3/order/place", json=self.payload(intent), headers=self._headers())
        data = _check(r)
        ids = data.get("data", {}).get("order_ids") or [data.get("data", {}).get("order_id")]
        if not ids or not ids[0]:
            raise UpstoxOrderError(f"no order id in response: {data}")
        return str(ids[0])

    async def modify(self, broker_order_id: str, *, quantity: int | None, price: object) -> None:
        body: dict[str, Any] = {"order_id": broker_order_id, "validity": "DAY"}
        if quantity is not None:
            body["quantity"] = quantity
        if price is not None:
            body["price"] = float(Decimal(str(price)))
        async with httpx.AsyncClient(
            base_url=self._base, transport=self._transport, timeout=10
        ) as c:
            r = await c.put("/v2/order/modify", json=body, headers=self._headers())
        _check(r)

    async def cancel(self, broker_order_id: str) -> None:
        async with httpx.AsyncClient(
            base_url=self._base, transport=self._transport, timeout=10
        ) as c:
            r = await c.delete(
                "/v2/order/cancel", params={"order_id": broker_order_id}, headers=self._headers()
            )
        _check(r)


def _check(r: httpx.Response) -> dict[str, Any]:
    try:
        data: dict[str, Any] = r.json()
    except ValueError as exc:
        raise UpstoxOrderError(f"non-JSON response {r.status_code}") from exc
    if r.status_code >= 400 or data.get("status") != "success":
        raise UpstoxOrderError(f"upstox rejected: {r.status_code} {data.get('errors') or data}")
    return data
