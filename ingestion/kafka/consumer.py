"""HarmoniConsumer — Avro-deserializing Kafka consumer with at-least-once delivery.

At-least-once guarantee:
- `enable.auto.commit = False` — offsets are NEVER committed automatically
- `commit(msg)` must be called explicitly AFTER successful processing
- On processing failure: do NOT call commit(); next poll() re-delivers the message
- On repeated failures: the message stays at the current offset until manually resolved

Usage:
    consumer = HarmoniConsumer.from_env(
        group_id="harmoni.scoring.intent",
        topics=[topics.WEB_PAGEVIEW, topics.EMAIL_ENGAGEMENT],
    )
    with consumer:
        while True:
            result = consumer.poll(timeout=1.0)
            if result is None:
                continue
            try:
                process(result.value)
                consumer.commit(result)      # commit only on success
            except ProcessingError:
                send_to_dlq(result)          # do NOT commit; re-process next poll
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from confluent_kafka import Consumer, KafkaError, KafkaException, Message

from ingestion.kafka.config import KafkaConfig
from ingestion.kafka.schema_registry import SchemaRegistryManager
from ingestion.kafka.topics import TopicConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConsumedMessage:
    """Deserialized Kafka message with routing metadata."""

    topic: str
    partition: int
    offset: int
    key: str | None
    value: dict[str, Any]
    raw_message: Message  # original confluent-kafka Message for commit


class HarmoniConsumer:
    """Kafka consumer with Avro deserialization and at-least-once delivery semantics."""

    def __init__(
        self,
        config: KafkaConfig,
        schema_manager: SchemaRegistryManager,
        group_id: str,
        topics: list[TopicConfig],
    ) -> None:
        self._schema = schema_manager
        self._consumer = Consumer(config.base_consumer_config(group_id))
        self._consumer.subscribe([t.name for t in topics])
        logger.info(
            "Consumer group=%s subscribed to: %s",
            group_id,
            [t.name for t in topics],
        )

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_env(
        cls,
        group_id: str,
        topics: list[TopicConfig],
    ) -> "HarmoniConsumer":
        """Create a consumer with settings loaded from environment variables."""
        cfg = KafkaConfig()
        schema_mgr = SchemaRegistryManager(cfg.schema_registry_url)
        return cls(cfg, schema_mgr, group_id, topics)

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    def poll(self, timeout: float = 1.0) -> ConsumedMessage | None:
        """Poll for one message and return a deserialized ConsumedMessage, or None.

        Args:
            timeout: Seconds to wait for a message. Returns None on timeout.

        Returns:
            ConsumedMessage on success.
            None on timeout, EOF, or non-fatal Kafka error.

        Raises:
            KafkaException: On fatal Kafka errors (cluster unreachable, etc.).
        """
        msg: Message | None = self._consumer.poll(timeout)

        if msg is None:
            return None

        if msg.error():
            err = msg.error()
            if err.code() == KafkaError._PARTITION_EOF:
                return None
            if err.fatal():
                raise KafkaException(err)
            logger.warning("Non-fatal Kafka error: %s", err)
            return None

        try:
            raw_bytes = msg.value()
            if raw_bytes is None:
                return None
            value = self._schema.deserialize(raw_bytes)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Deserialization failed: topic=%s partition=%d offset=%d error=%s",
                msg.topic(),
                msg.partition(),
                msg.offset(),
                exc,
            )
            return None

        key_bytes = msg.key()
        key = key_bytes.decode("utf-8") if key_bytes else None

        return ConsumedMessage(
            topic=msg.topic(),
            partition=msg.partition(),
            offset=msg.offset(),
            key=key,
            value=value,
            raw_message=msg,
        )

    def batch_poll(
        self,
        max_messages: int = 100,
        timeout: float = 1.0,
    ) -> list[ConsumedMessage]:
        """Poll up to *max_messages* in one call.

        Returns an empty list if no messages are available within *timeout*.
        """
        messages = self._consumer.consume(num_messages=max_messages, timeout=timeout)
        results: list[ConsumedMessage] = []

        for msg in messages:
            if msg.error():
                err = msg.error()
                if err.code() != KafkaError._PARTITION_EOF:
                    logger.warning("Kafka error in batch: %s", err)
                continue
            try:
                value = self._schema.deserialize(msg.value())
            except Exception as exc:  # noqa: BLE001
                logger.error("Deserialization error in batch: %s", exc)
                continue

            key_bytes = msg.key()
            results.append(
                ConsumedMessage(
                    topic=msg.topic(),
                    partition=msg.partition(),
                    offset=msg.offset(),
                    key=key_bytes.decode("utf-8") if key_bytes else None,
                    value=value,
                    raw_message=msg,
                )
            )

        return results

    # ------------------------------------------------------------------
    # Offset management (at-least-once contract)
    # ------------------------------------------------------------------

    def commit(self, message: ConsumedMessage) -> None:
        """Synchronously commit the offset for a successfully processed message.

        Must be called AFTER processing is complete and durable.
        Never call this before processing — it would advance the offset
        and cause the message to be skipped on restart.
        """
        self._consumer.commit(message=message.raw_message, asynchronous=False)
        logger.debug(
            "Committed: topic=%s partition=%d offset=%d",
            message.topic,
            message.partition,
            message.offset,
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the consumer and release resources. Commits pending offsets."""
        self._consumer.close()

    def __enter__(self) -> "HarmoniConsumer":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
