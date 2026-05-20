"""Circuit breakers for all external API calls.

Every outbound integration (HubSpot, Salesloft, Slack, enrichment providers)
must be wrapped in a circuit breaker so a downstream failure doesn't cascade
into the harmoni API or NBA dispatch pipeline.

Pattern:
  - CLOSED: requests pass through normally.
  - OPEN: requests fail immediately with CircuitOpenError (no network call).
  - HALF-OPEN: one probe request is allowed through to test recovery.

Thresholds (conservative defaults; tune per integration SLA):
  - failure_threshold: 5 consecutive failures → OPEN
  - recovery_timeout: 30 seconds in OPEN before allowing probe
  - success_threshold: 2 consecutive successes in HALF-OPEN → CLOSED

Usage::

    from api.circuit_breakers import get_circuit_breaker

    breaker = get_circuit_breaker("hubspot")

    @breaker
    async def call_hubspot(task_type: str, account_id: str) -> dict:
        ...
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from enum import Enum, auto
from functools import wraps
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


class CircuitState(Enum):
    CLOSED    = auto()
    OPEN      = auto()
    HALF_OPEN = auto()


class CircuitOpenError(Exception):
    """Raised when a call is rejected because the circuit is OPEN."""

    def __init__(self, name: str, retry_after: float) -> None:
        self.name = name
        self.retry_after = retry_after
        super().__init__(
            f"Circuit '{name}' is OPEN — retry after {retry_after:.1f}s"
        )


class CircuitBreaker:
    """Thread-safe (asyncio-safe) circuit breaker.

    Args:
        name: Human-readable integration name (used in logs and errors).
        failure_threshold: Consecutive failures before tripping to OPEN.
        recovery_timeout: Seconds to wait in OPEN before probing (HALF-OPEN).
        success_threshold: Consecutive successes in HALF-OPEN to reset to CLOSED.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        success_threshold: int = 2,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._opened_at: float | None = None
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def is_open(self) -> bool:
        return self._state == CircuitState.OPEN

    def _retry_after(self) -> float:
        if self._opened_at is None:
            return 0.0
        elapsed = time.monotonic() - self._opened_at
        return max(0.0, self.recovery_timeout - elapsed)

    async def _allow_request(self) -> bool:
        async with self._lock:
            if self._state == CircuitState.CLOSED:
                return True

            if self._state == CircuitState.OPEN:
                if time.monotonic() - (self._opened_at or 0) >= self.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._success_count = 0
                    logger.info("Circuit '%s' → HALF-OPEN (probing)", self.name)
                    return True
                return False  # still OPEN

            # HALF_OPEN: allow one probe at a time
            return True

    async def _record_success(self) -> None:
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._opened_at = None
                    logger.info("Circuit '%s' → CLOSED (recovered)", self.name)
            elif self._state == CircuitState.CLOSED:
                self._failure_count = 0  # reset on any success

    async def _record_failure(self) -> None:
        async with self._lock:
            self._failure_count += 1
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                self._opened_at = time.monotonic()
                logger.warning(
                    "Circuit '%s' probe failed → OPEN again (retry in %.0fs)",
                    self.name,
                    self.recovery_timeout,
                )
            elif (
                self._state == CircuitState.CLOSED
                and self._failure_count >= self.failure_threshold
            ):
                self._state = CircuitState.OPEN
                self._opened_at = time.monotonic()
                logger.error(
                    "Circuit '%s' TRIPPED → OPEN after %d failures (retry in %.0fs)",
                    self.name,
                    self._failure_count,
                    self.recovery_timeout,
                )

    def __call__(self, func: F) -> F:
        """Decorator that wraps an async function with this circuit breaker."""

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not await self._allow_request():
                raise CircuitOpenError(self.name, self._retry_after())

            try:
                result = await func(*args, **kwargs)
                await self._record_success()
                return result
            except CircuitOpenError:
                raise
            except Exception:
                await self._record_failure()
                raise

        return wrapper  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Registry — one breaker instance per integration, shared across requests
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, CircuitBreaker] = {}

_BREAKER_CONFIGS: dict[str, dict[str, Any]] = {
    "hubspot": {
        "failure_threshold": 5,
        "recovery_timeout": 30.0,
        "success_threshold": 2,
    },
    "salesloft": {
        "failure_threshold": 5,
        "recovery_timeout": 30.0,
        "success_threshold": 2,
    },
    "slack": {
        "failure_threshold": 10,  # Slack is informational — more lenient
        "recovery_timeout": 60.0,
        "success_threshold": 3,
    },
    "clearbit_enrichment": {
        "failure_threshold": 3,
        "recovery_timeout": 120.0,  # enrichment provider has longer recovery window
        "success_threshold": 2,
    },
    "openai_embeddings": {
        "failure_threshold": 5,
        "recovery_timeout": 60.0,
        "success_threshold": 2,
    },
}


def get_circuit_breaker(name: str) -> CircuitBreaker:
    """Return the singleton CircuitBreaker for the named integration.

    Creates the breaker on first call using the config in _BREAKER_CONFIGS,
    or defaults (5 / 30s / 2) if the name is not pre-configured.
    """
    if name not in _REGISTRY:
        config = _BREAKER_CONFIGS.get(name, {})
        _REGISTRY[name] = CircuitBreaker(name=name, **config)
    return _REGISTRY[name]


def circuit_breaker_status() -> dict[str, dict[str, Any]]:
    """Return the current state of all registered circuit breakers.

    Used by the /health endpoint to surface integration health.
    """
    return {
        name: {
            "state": cb.state.name,
            "failure_count": cb._failure_count,
            "retry_after_seconds": cb._retry_after() if cb.is_open else None,
        }
        for name, cb in _REGISTRY.items()
    }
