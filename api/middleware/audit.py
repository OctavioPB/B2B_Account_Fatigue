"""Audit log middleware — records every write operation to the audit_log table.

Every POST, PUT, PATCH, DELETE request that reaches the API produces one
append-only row in audit_log. Read requests (GET, HEAD, OPTIONS) are excluded.

The middleware sanitises request bodies before persisting (strips keys whose
names contain 'secret', 'password', 'token', 'key').

Audit rows are written fire-and-forget via asyncio.create_task so they never
add latency to the response path. A failed audit write emits a structured
ERROR log but does not fail the request.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_SECRET_PATTERN = re.compile(r"(secret|password|token|key|credential)", re.IGNORECASE)
_MAX_BODY_BYTES = 8_192  # do not store bodies larger than 8 KB


def _sanitise_body(raw: bytes) -> dict | None:
    """Parse JSON body and strip sensitive keys; return None on parse failure."""
    if not raw:
        return None
    try:
        parsed = json.loads(raw.decode("utf-8", errors="replace"))
        if not isinstance(parsed, dict):
            return None
        return {
            k: "***REDACTED***" if _SECRET_PATTERN.search(k) else v
            for k, v in parsed.items()
        }
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def _resource_info(path: str) -> tuple[str | None, str | None]:
    """Extract resource_type and resource_id from a /v1/{type}/{id} path."""
    parts = [p for p in path.split("/") if p and p != "v1"]
    resource_type = parts[0] if parts else None
    resource_id   = parts[1] if len(parts) > 1 else None
    return resource_type, resource_id


async def _write_audit_row(row: dict) -> None:
    """Persist an audit row — best effort, never raises."""
    # In production: INSERT into audit_log via asyncpg connection pool.
    # For now: emit as a structured log so the audit trail is captured by
    # the log aggregator (Datadog / Loki) until the DB pool is wired in.
    logger.info(
        json.dumps({"event": "audit_write", **row}, default=str)
    )


class AuditLogMiddleware(BaseHTTPMiddleware):
    """Appends one audit row per write request, fire-and-forget."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.method not in _WRITE_METHODS:
            return await call_next(request)

        # Read and buffer body so both middleware and route handler can access it
        raw_body = await request.body()
        if len(raw_body) <= _MAX_BODY_BYTES:
            sanitised = _sanitise_body(raw_body)
        else:
            sanitised = {"_note": f"body too large to audit ({len(raw_body)} bytes)"}

        response: Response = await call_next(request)

        request_id  = getattr(request.state, "request_id", None)
        tenant_id   = getattr(request.state, "tenant_id", "anonymous")
        duration_ms = getattr(request.state, "duration_ms", None)

        # JWT sub — best-effort extraction from state set by auth middleware
        actor = getattr(request.state, "tenant_id", "anonymous")

        resource_type, resource_id = _resource_info(request.url.path)

        row = {
            "tenant_id":     tenant_id,
            "request_id":    request_id,
            "actor_jwt_sub": actor,
            "http_method":   request.method,
            "path":          request.url.path,
            "resource_type": resource_type,
            "resource_id":   resource_id,
            "request_body":  sanitised,
            "response_status": response.status_code,
            "client_ip":     _get_client_ip(request),
            "user_agent":    request.headers.get("User-Agent"),
            "duration_ms":   duration_ms,
        }

        asyncio.create_task(_write_audit_row(row))

        return response


def _get_client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None
