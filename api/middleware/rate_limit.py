"""Redis fixed-window rate limiting middleware.

Uses Redis INCR + EXPIRE to count requests per tenant per 60-second window.
Returns 429 Too Many Requests when the tenant's rpm limit is exceeded.

Fail-open: if Redis is unavailable, requests are allowed through and a warning
is logged. This prevents Redis downtime from taking down the API.
"""

from __future__ import annotations

import json
import logging
from typing import Callable

import redis.asyncio as aioredis
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

_WINDOW_SECONDS = 60


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Fixed-window rate limiter backed by Redis.

    Rate limit is tenant-aware: each authenticated tenant has its own counter.
    Unauthenticated requests (e.g. /health) are exempt.
    """

    def __init__(self, app, redis_client: aioredis.Redis, default_rpm: int = 60) -> None:
        super().__init__(app)
        self._redis = redis_client
        self._default_rpm = default_rpm

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Health check and other exempt paths pass through
        if _is_exempt(request.url.path):
            return await call_next(request)

        tenant_id = _extract_tenant_id(request)
        if tenant_id is None:
            # No tenant context yet (auth will reject it downstream)
            return await call_next(request)

        rpm_limit = getattr(request.state, "rate_limit_rpm", self._default_rpm)
        key = f"ratelimit:{tenant_id}:{_window_key()}"

        try:
            count = await self._redis.incr(key)
            if count == 1:
                await self._redis.expire(key, _WINDOW_SECONDS)

            request.state.rate_limit_remaining = max(0, rpm_limit - count)

            if count > rpm_limit:
                logger.warning(
                    json.dumps(
                        {
                            "event": "rate_limit_exceeded",
                            "tenant_id": tenant_id,
                            "count": count,
                            "limit": rpm_limit,
                            "path": request.url.path,
                        }
                    )
                )
                return Response(
                    content=json.dumps(
                        {
                            "error": "Rate limit exceeded",
                            "code": "RATE_LIMIT_EXCEEDED",
                            "retry_after_seconds": _WINDOW_SECONDS,
                        }
                    ),
                    status_code=429,
                    headers={
                        "Content-Type": "application/json",
                        "Retry-After": str(_WINDOW_SECONDS),
                        "X-RateLimit-Limit": str(rpm_limit),
                        "X-RateLimit-Remaining": "0",
                    },
                )

        except Exception as exc:  # noqa: BLE001 — fail-open on Redis errors
            logger.warning("Rate limit Redis error (fail-open): %s", exc)

        response = await call_next(request)
        remaining = getattr(request.state, "rate_limit_remaining", rpm_limit)
        response.headers["X-RateLimit-Limit"] = str(rpm_limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response


def _is_exempt(path: str) -> bool:
    return path in {"/health", "/docs", "/redoc", "/openapi.json"}


def _extract_tenant_id(request: Request) -> str | None:
    """Best-effort tenant extraction from Authorization header without full decode."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    # Use request.state if already decoded by a prior middleware
    return getattr(request.state, "tenant_id", None)


def _window_key() -> str:
    """Current 60-second window bucket (unix timestamp // 60)."""
    import time
    return str(int(time.time()) // _WINDOW_SECONDS)
