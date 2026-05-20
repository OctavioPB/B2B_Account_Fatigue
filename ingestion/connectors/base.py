"""Base connector class for all harmoni source connectors.

Each connector is responsible for:
1. Receiving a raw event from its source (webhook payload, poll response, etc.)
2. Normalizing it to the canonical Avro schema for its topic
3. Resolving the account_domain via normalize_domain()
4. Producing to the correct Kafka topic via HarmoniProducer

Connectors are stateless — they hold a reference to a shared HarmoniProducer
and a SchemaRegistryManager, both injected at construction time.
"""

from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from identity.resolver import normalize_domain, is_free_email_domain
from ingestion.kafka.producer import HarmoniProducer
from ingestion.kafka.topics import TopicConfig

logger = logging.getLogger(__name__)


class BaseConnector(ABC):
    """Abstract base for all harmoni source connectors."""

    def __init__(self, producer: HarmoniProducer) -> None:
        self._producer = producer

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def ingest(self, raw_event: dict[str, Any]) -> None:
        """Normalize *raw_event* and produce it to Kafka.

        Args:
            raw_event: Source-system payload (webhook body, API response, etc.).
        """
        try:
            account_domain, normalized = self.normalize(raw_event)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "%s: normalization failed for event %r: %s — skipping",
                self.__class__.__name__,
                raw_event,
                exc,
            )
            return

        if account_domain is None:
            logger.debug(
                "%s: could not resolve account_domain — event quarantined",
                self.__class__.__name__,
            )
            return

        self._producer.produce(self.topic, normalized, account_domain)

    @abstractmethod
    def normalize(
        self, raw_event: dict[str, Any]
    ) -> tuple[str | None, dict[str, Any]]:
        """Normalize a raw source event to the canonical Avro schema.

        Returns:
            (account_domain, avro_compatible_dict) or (None, {}) if unresolvable.
        """

    @abstractmethod
    def generate_mock_event(self) -> dict[str, Any]:
        """Generate a realistic mock raw event for testing and load simulation."""

    @property
    @abstractmethod
    def topic(self) -> TopicConfig:
        """The target Kafka topic for this connector."""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _new_event_id() -> str:
        return str(uuid.uuid4())

    @staticmethod
    def _now_ms() -> int:
        return int(datetime.now(timezone.utc).timestamp() * 1000)

    @staticmethod
    def _resolve_domain(email: str) -> str | None:
        """Return normalized domain or None if free-email / invalid."""
        domain = normalize_domain(email)
        if is_free_email_domain(domain):
            return None
        return domain

    def ingest_mock(self) -> None:
        """Generate and ingest one mock event. Useful for load testing and demos."""
        self.ingest(self.generate_mock_event())
