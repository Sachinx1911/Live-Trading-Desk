"""Request logging + request id. Audit of state-changing calls is done per-router via
`api.deps.audit` so it has access to the user and entity."""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from core.logging import get_logger

log = get_logger("api.request")


class RequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        structlog.contextvars.bind_contextvars(request_id=request_id)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.unbind_contextvars("request_id")
        duration_ms = (time.perf_counter() - start) * 1000
        response.headers["x-request-id"] = request_id
        if not request.url.path.endswith("/health"):
            log.info(
                "http",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                ms=round(duration_ms, 1),
                request_id=request_id,
            )
        return response
