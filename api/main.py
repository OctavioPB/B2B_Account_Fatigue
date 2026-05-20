"""harmoni FastAPI application factory.

Usage:
    uvicorn api.main:app --reload

Or in tests:
    from api.main import create_app
    app = create_app(settings_override=...)
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

import redis.asyncio as aioredis
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.config import Settings, get_settings
from api.exceptions import (
    AccountNotFoundError,
    CooldownActiveError,
    FeatureDisabledError,
    HarmoniError,
    InvalidDomainError,
    TenantIsolationError,
    TenantNotFoundError,
)
from api.middleware.audit import AuditLogMiddleware
from api.middleware.logging import RequestLoggingMiddleware, configure_logging
from api.middleware.rate_limit import RateLimitMiddleware
from api.middleware.security import SecurityHeadersMiddleware
from api.routers import accounts, health, tenants, webhooks
from api.circuit_breakers import circuit_breaker_status

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exception → HTTP status mapping
# ---------------------------------------------------------------------------

_EXCEPTION_STATUS: dict[type[HarmoniError], int] = {
    AccountNotFoundError: status.HTTP_404_NOT_FOUND,
    InvalidDomainError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    TenantNotFoundError: status.HTTP_401_UNAUTHORIZED,
    TenantIsolationError: status.HTTP_403_FORBIDDEN,
    CooldownActiveError: status.HTTP_409_CONFLICT,
    FeatureDisabledError: status.HTTP_503_SERVICE_UNAVAILABLE,
}


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        settings: Optional Settings override (useful in tests).
    """
    cfg = settings or get_settings()

    configure_logging(level=cfg.log_level, json_logs=cfg.log_json)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        redis_client = aioredis.from_url(cfg.redis_url, decode_responses=True)
        app.state.redis = redis_client
        logger.info("harmoni API starting — redis=%s", cfg.redis_url)
        yield
        await redis_client.aclose()
        logger.info("harmoni API shutdown complete")

    app = FastAPI(
        title="harmoni — Revenue Intelligence API",
        description=(
            "Account-level fatigue, intent, and churn signals with Next Best Action "
            "recommendations for B2B revenue teams. "
            "This is a **Revenue Intelligence & Deal Protection** platform."
        ),
        version="1.0.0",
        lifespan=lifespan,
        openapi_tags=[
            {"name": "health", "description": "Liveness probes"},
            {"name": "accounts", "description": "Account health signals and NBA recommendations"},
            {"name": "webhooks", "description": "Outbound webhook subscriptions"},
            {"name": "tenants (admin)", "description": "Tenant provisioning (admin only)"},
        ],
    )

    # ------------------------------------------------------------------
    # Middleware (order matters — outermost first in the call stack)
    # ------------------------------------------------------------------

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # OWASP security headers — outermost so every response is covered
    app.add_middleware(SecurityHeadersMiddleware)

    app.add_middleware(RequestLoggingMiddleware)

    # Audit log for all write operations (POST/PUT/PATCH/DELETE)
    app.add_middleware(AuditLogMiddleware)

    if cfg.rate_limit_enabled:
        redis_for_rl = aioredis.from_url(cfg.redis_url, decode_responses=True)
        app.add_middleware(
            RateLimitMiddleware,
            redis_client=redis_for_rl,
            default_rpm=cfg.rate_limit_rpm_default,
        )

    # ------------------------------------------------------------------
    # Routers
    # ------------------------------------------------------------------

    app.include_router(health.router)
    app.include_router(accounts.router)
    app.include_router(tenants.router)
    app.include_router(webhooks.router)

    # ------------------------------------------------------------------
    # Exception handlers
    # ------------------------------------------------------------------

    @app.exception_handler(HarmoniError)
    async def harmoni_error_handler(request: Request, exc: HarmoniError) -> JSONResponse:
        http_status = _EXCEPTION_STATUS.get(type(exc), status.HTTP_500_INTERNAL_SERVER_ERROR)
        request_id = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=http_status,
            content={
                "error": exc.message,
                "code": exc.code,
                "request_id": request_id,
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        request_id = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "Internal server error",
                "code": "INTERNAL_ERROR",
                "request_id": request_id,
            },
        )

    return app


# ---------------------------------------------------------------------------
# Module-level app instance (used by uvicorn and pytest)
# ---------------------------------------------------------------------------

app = create_app()
