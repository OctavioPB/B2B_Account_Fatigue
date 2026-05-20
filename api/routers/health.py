"""Health check endpoints — no auth, no versioning prefix."""

from __future__ import annotations

from fastapi import APIRouter

from api.circuit_breakers import circuit_breaker_status

router = APIRouter(tags=["health"])


@router.get("/health", include_in_schema=True)
async def health() -> dict:
    """Liveness probe with circuit breaker status for all external integrations."""
    breakers = circuit_breaker_status()
    any_open = any(b["state"] == "OPEN" for b in breakers.values())
    return {
        "status": "ok",
        "service": "harmoni-api",
        "integrations": breakers,
        "degraded": any_open,
    }
