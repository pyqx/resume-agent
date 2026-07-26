"""Structured request logging middleware with request-id propagation."""

import contextvars
import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("resume_agent.api")

# Business code can read this to correlate its own logs with a request.
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)

_QUIET_PATHS = {"/health"}


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Honor an inbound id (proxy/frontend) or mint one.
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        token = request_id_var.set(request_id)
        start = time.perf_counter()

        try:
            response: Response = await call_next(request)
        except Exception:
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.exception(
                "request failed rid=%s %s %s elapsed_ms=%.1f",
                request_id, request.method, request.url.path, elapsed_ms,
            )
            request_id_var.reset(token)
            raise

        elapsed_ms = (time.perf_counter() - start) * 1000
        if request.url.path not in _QUIET_PATHS:
            logger.info(
                "rid=%s %s %s status=%d elapsed_ms=%.1f",
                request_id, request.method, request.url.path,
                response.status_code, elapsed_ms,
            )
        response.headers["X-Request-ID"] = request_id
        request_id_var.reset(token)
        return response
