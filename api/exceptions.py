"""Custom exception classes for the harmoni FastAPI application.

All exceptions must inherit from HarmoniError. Never raise bare Exception.
HTTP exceptions should use these classes so middleware can serialize them
consistently via the global exception handler.
"""

from __future__ import annotations


class HarmoniError(Exception):
    """Base class for all harmoni application exceptions."""

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or self.__class__.__name__


# ---------------------------------------------------------------------------
# Domain errors
# ---------------------------------------------------------------------------


class AccountNotFoundError(HarmoniError):
    """Raised when an account domain cannot be found in the datastore."""


class InvalidDomainError(HarmoniError):
    """Raised when a supplied domain fails normalization or validation."""


class TenantNotFoundError(HarmoniError):
    """Raised when a JWT tenant_id has no corresponding tenant record."""


class TenantIsolationError(HarmoniError):
    """Raised when a request attempts to access another tenant's data."""


class CooldownActiveError(HarmoniError):
    """Raised when an action is attempted while an ActionCooldown lock is set."""


# ---------------------------------------------------------------------------
# Infrastructure errors
# ---------------------------------------------------------------------------


class SchemaRegistryError(HarmoniError):
    """Raised when the Confluent Schema Registry rejects a schema operation."""


class KafkaProducerError(HarmoniError):
    """Raised when a Kafka producer fails to deliver a message."""


class ScoringUnavailableError(HarmoniError):
    """Raised when the scoring engine cannot compute a score (e.g. insufficient signals)."""


# ---------------------------------------------------------------------------
# Feature flag errors
# ---------------------------------------------------------------------------


class FeatureDisabledError(HarmoniError):
    """Raised when code guarded by a feature flag is invoked while the flag is off."""
