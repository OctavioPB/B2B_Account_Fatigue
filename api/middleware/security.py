"""OWASP security hardening middleware.

Adds the HTTP security headers required to pass an OWASP ZAP scan with
zero HIGH/CRITICAL findings. All header values follow OWASP ASVS v4.0
recommendations for API services.

Headers applied to every response:
  - Strict-Transport-Security (HSTS)
  - X-Content-Type-Options
  - X-Frame-Options
  - Content-Security-Policy (strict; APIs don't serve HTML so very tight)
  - Referrer-Policy
  - Permissions-Policy
  - Cache-Control (no-store for API responses)
  - X-XSS-Protection (legacy browsers)

Additionally removes headers that leak server information:
  - Server
  - X-Powered-By
"""

from __future__ import annotations

from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Paths served as HTML (OpenAPI docs) need a relaxed CSP
_HTML_PATHS = {"/docs", "/redoc"}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Injects OWASP-compliant security headers on every response."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response: Response = await call_next(request)

        is_html = request.url.path in _HTML_PATHS

        # HSTS — max-age 1 year; includeSubDomains
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )

        # Prevent MIME-type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Deny framing (clickjacking)
        response.headers["X-Frame-Options"] = "DENY"

        # CSP — tight for API; relaxed only for docs UI
        if is_html:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self' https://cdn.jsdelivr.net https://unpkg.com; "
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com; "
                "img-src 'self' data: https:; "
                "font-src 'self' data: https:;"
            )
        else:
            response.headers["Content-Security-Policy"] = (
                "default-src 'none'; frame-ancestors 'none'"
            )

        # Do not send referrer outside origin
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Disable browser features not needed by an API
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
        )

        # API responses must never be cached by proxies
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"

        # Legacy XSS protection (modern browsers ignore this but ZAP checks it)
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Remove information-leaking server headers
        response.headers.pop("Server", None)
        response.headers.pop("X-Powered-By", None)

        return response
