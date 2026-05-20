"""Kafka topic administration — create topics and verify cluster health.

Used at service startup to ensure all required topics exist before
producers or consumers attempt to connect.

Usage:
    from ingestion.kafka.admin import ensure_topics_exist
    ensure_topics_exist(bootstrap_servers="localhost:9092")
"""

from __future__ import annotations

import logging
from typing import Sequence

from confluent_kafka.admin import AdminClient, NewTopic

from ingestion.kafka.topics import ALL_TOPICS, TopicConfig

logger = logging.getLogger(__name__)


def build_admin_client(bootstrap_servers: str) -> AdminClient:
    """Create and return a confluent-kafka AdminClient."""
    return AdminClient({"bootstrap.servers": bootstrap_servers})


def ensure_topics_exist(
    bootstrap_servers: str,
    topics: Sequence[TopicConfig] = ALL_TOPICS,
    *,
    timeout_seconds: float = 30.0,
) -> dict[str, bool]:
    """Create any topics that do not already exist.

    Idempotent — safe to call on every service startup.

    Args:
        bootstrap_servers: Kafka bootstrap broker string.
        topics: Topic configs to ensure exist. Defaults to ALL_TOPICS.
        timeout_seconds: Max time to wait for each topic creation future.

    Returns:
        Dict mapping topic name → True (created) or False (already existed).
    """
    admin = build_admin_client(bootstrap_servers)
    existing = _list_existing_topics(admin)

    to_create = [t for t in topics if t.name not in existing]
    if not to_create:
        logger.info("All %d topics already exist; nothing to create.", len(topics))
        return {t.name: False for t in topics}

    new_topics = [
        NewTopic(
            topic=t.name,
            num_partitions=t.partitions,
            replication_factor=t.replication_factor,
            config=t.to_confluent_config(),
        )
        for t in to_create
    ]

    results: dict[str, bool] = {t.name: False for t in topics}
    futures = admin.create_topics(new_topics)

    for topic_name, future in futures.items():
        try:
            future.result(timeout=timeout_seconds)
            logger.info("Created topic: %s", topic_name)
            results[topic_name] = True
        except Exception as exc:  # noqa: BLE001
            # Topic may already exist — treat as non-fatal
            logger.warning("Topic creation result for %s: %s", topic_name, exc)

    return results


def delete_topics(
    bootstrap_servers: str,
    topic_names: Sequence[str],
    *,
    timeout_seconds: float = 30.0,
) -> None:
    """Delete topics by name. Intended for test teardown only."""
    admin = build_admin_client(bootstrap_servers)
    futures = admin.delete_topics(list(topic_names))
    for name, future in futures.items():
        try:
            future.result(timeout=timeout_seconds)
            logger.info("Deleted topic: %s", name)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to delete topic %s: %s", name, exc)


def _list_existing_topics(admin: AdminClient) -> set[str]:
    """Return the set of topic names that currently exist in the cluster."""
    metadata = admin.list_topics(timeout=10)
    return {name for name, meta in metadata.topics.items() if meta.error is None}
