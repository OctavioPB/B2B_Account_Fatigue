"""HarmoniProducer — Avro-serialized Kafka producer with DLQ routing.

Design:
- Messages are keyed by account_domain for per-account ordering
- Schema validation via Confluent Schema Registry before every produce
- Serialization failures and delivery errors route to harmoni.dlq
- DLQ schema is always registered first; DLQ produce is last-resort (logs on failure)
- Thread-safe: a single producer instance may be shared across connectors

Usage:
    producer = HarmoniProducer.from_env()
    producer.produce(topics.WEB_PAGEVIEW, event_dict, account_domain="acme.com")
    producer.flush()
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from confluent_kafka import KafkaError, Message, Producer

from ingestion.kafka.config import KafkaConfig
from ingestion.kafka.schema_registry import SchemaRegistryManager
from ingestion.kafka.topics import DLQ, TopicConfig

logger = logging.getLogger(__name__)


class HarmoniProducer:
    """Kafka producer with Avro serialization, schema enforcement, and DLQ routing."""

    def __init__(
        self,
        config: KafkaConfig,
        schema_manager: SchemaRegistryManager,
    ) -> None:
        self._producer = Producer(config.base_producer_config())
        self._schema = schema_manager

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_env(cls) -> "HarmoniProducer":
        """Create a producer with settings loaded from environment variables."""
        cfg = KafkaConfig()
        schema_mgr = SchemaRegistryManager(cfg.schema_registry_url)
        schema_mgr.register_all()
        return cls(cfg, schema_mgr)

    # ------------------------------------------------------------------
    # Core produce
    # ------------------------------------------------------------------

    def produce(
        self,
        topic: TopicConfig,
        value: dict[str, Any],
        account_domain: str,
    ) -> None:
        """Produce a schema-validated Avro message keyed by account_domain.

        On serialization failure the original dict is routed to the DLQ with
        a SERIALIZATION or SCHEMA_VALIDATION failure stage.

        Args:
            topic:          Target TopicConfig (from ingestion.kafka.topics).
            value:          Message payload matching the topic's Avro schema.
            account_domain: Normalized account domain used as the Kafka message key.
        """
        try:
            serialized = self._schema.serialize(topic.schema_subject, value)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Serialization failed for topic=%s domain=%s: %s — routing to DLQ",
                topic.name,
                account_domain,
                exc,
            )
            stage = (
                "SCHEMA_VALIDATION"
                if "ValidationError" in type(exc).__name__
                else "SERIALIZATION"
            )
            self._produce_to_dlq(
                source_topic=topic.name,
                original_key=account_domain.encode("utf-8"),
                original_value=_safe_json_bytes(value),
                error=exc,
                failure_stage=stage,
            )
            return

        self._producer.produce(
            topic=topic.name,
            key=account_domain.encode("utf-8"),
            value=serialized,
            on_delivery=self._delivery_callback,
        )
        # poll() triggers delivery callbacks without blocking
        self._producer.poll(0)

    # ------------------------------------------------------------------
    # DLQ
    # ------------------------------------------------------------------

    def _produce_to_dlq(
        self,
        source_topic: str,
        original_key: bytes | None,
        original_value: bytes | None,
        error: Exception,
        failure_stage: str = "SERIALIZATION",
        source_partition: int = -1,
        source_offset: int = -1,
    ) -> None:
        envelope: dict[str, Any] = {
            "envelope_id": str(uuid.uuid4()),
            "source_topic": source_topic,
            "source_partition": source_partition,
            "source_offset": source_offset,
            "error_class": type(error).__name__,
            "error_message": str(error)[:2048],
            "original_key": original_key,
            "original_value": original_value,
            "failure_stage": failure_stage,
            "failed_at": _now_ms(),
        }
        try:
            serialized = self._schema.serialize(DLQ.schema_subject, envelope)
            self._producer.produce(
                topic=DLQ.name,
                key=source_topic.encode("utf-8"),
                value=serialized,
                on_delivery=self._delivery_callback,
            )
            self._producer.poll(0)
            logger.info(
                "DLQ: routed failed message from topic=%s stage=%s error=%s",
                source_topic,
                failure_stage,
                type(error).__name__,
            )
        except Exception as dlq_exc:  # noqa: BLE001
            # Last resort: if DLQ produce fails, log full context to stderr
            logger.error(
                "CRITICAL: DLQ produce also failed. Original error: %s. DLQ error: %s. "
                "source_topic=%s key=%r value=%r",
                error,
                dlq_exc,
                source_topic,
                original_key,
                original_value,
            )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def flush(self, timeout: float = 30.0) -> int:
        """Wait for all outstanding produce requests to complete.

        Returns:
            Number of messages still in the queue (0 means all delivered).
        """
        remaining = self._producer.flush(timeout)
        if remaining > 0:
            logger.warning("flush() timed out with %d messages undelivered.", remaining)
        return remaining

    def __enter__(self) -> "HarmoniProducer":
        return self

    def __exit__(self, *_: object) -> None:
        self.flush()

    # ------------------------------------------------------------------
    # Delivery callback
    # ------------------------------------------------------------------

    @staticmethod
    def _delivery_callback(err: KafkaError | None, msg: Message) -> None:
        if err:
            logger.error(
                "Delivery failed: topic=%s partition=%s offset=%s error=%s",
                msg.topic(),
                msg.partition(),
                msg.offset(),
                err,
            )
        else:
            logger.debug(
                "Delivered: topic=%s partition=%d offset=%d",
                msg.topic(),
                msg.partition(),
                msg.offset(),
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _safe_json_bytes(value: dict[str, Any]) -> bytes:
    """Serialize dict to JSON bytes, replacing non-serializable values with their repr."""
    try:
        return json.dumps(value, default=str).encode("utf-8")
    except Exception:  # noqa: BLE001
        return repr(value).encode("utf-8")
