"""Structured JSON logging middleware.

Injects X-Request-ID into every response and logs request/response metadata
as structured JSON so log aggregators (Datadog, CloudWatch, etc.) can parse
without regex.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("harmoni.access")

_REQUEST_ID_HEADER = "X-Request-ID"


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Adds X-Request-ID and emits a structured access log line per request."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get(_REQUEST_ID_HEADER) or str(uuid.uuid4())

        # Make the request_id available to downstream code via request.state
        request.state.request_id = request_id

        start = time.perf_counter()
        response: Response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        response.headers[_REQUEST_ID_HEADER] = request_id

        logger.info(
            json.dumps(
                {
                    "event": "http_request",
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "query": str(request.url.query) or None,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                    "client_ip": _get_client_ip(request),
                },
                default=str,
            )
        )

        return response


def _get_client_ip(request: Request) -> str | None:
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def configure_logging(level: str = "INFO", json_logs: bool = True) -> None:
    """Configure root logger; called once at application startup."""
    log_level = getattr(logging, level.upper(), logging.INFO)

    if json_logs:
        handler = logging.StreamHandler()
        handler.setFormatter(_JsonFormatter())
        logging.basicConfig(level=log_level, handlers=[handler], force=True)
    else:
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s %(levelname)s %(name)s — %(message)s",
            force=True,
        )


class _JsonFormatter(logging.Formatter):
    """Formats all non-access log lines as JSON."""

    def format(self, record: logging.LogRecord) -> str:
        # access logger already emits pre-serialised JSON
        if record.name == "harmoni.access":
            return record.getMessage()

        payload: dict = {
            "ts": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)
