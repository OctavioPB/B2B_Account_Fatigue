"""Integration tests: produce → consume round-trip for all four connectors.

These tests require a running Kafka + Schema Registry (docker-compose up).
Run with: pytest -m integration -v

Each test:
1. Registers schemas with the real Schema Registry
2. Ensures topics exist
3. Produces a mock event via the connector
4. Consumes from the topic and verifies the deserialized value matches
"""

from __future__ import annotations

import os
import time
import uuid
from typing import Any

import pytest

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
SCHEMA_REGISTRY_URL = os.getenv("KAFKA_SCHEMA_REGISTRY_URL", "http://localhost:8081")


@pytest.fixture(scope="module")
def kafka_config() -> Any:
    from ingestion.kafka.config import KafkaConfig
    return KafkaConfig(
        bootstrap_servers=KAFKA_BOOTSTRAP,
        schema_registry_url=SCHEMA_REGISTRY_URL,
    )


@pytest.fixture(scope="module")
def schema_manager(kafka_config: Any) -> Any:
    from ingestion.kafka.schema_registry import SchemaRegistryManager
    mgr = SchemaRegistryManager(SCHEMA_REGISTRY_URL)
    mgr.register_all()
    return mgr


@pytest.fixture(scope="module", autouse=True)
def ensure_topics(kafka_config: Any) -> None:
    from ingestion.kafka.admin import ensure_topics_exist
    ensure_topics_exist(KAFKA_BOOTSTRAP)


@pytest.fixture(scope="module")
def producer(kafka_config: Any, schema_manager: Any) -> Any:
    from ingestion.kafka.producer import HarmoniProducer
    p = HarmoniProducer(kafka_config, schema_manager)
    yield p
    p.flush()


def _make_consumer(schema_manager: Any, kafka_config: Any, topic: Any) -> Any:
    from ingestion.kafka.consumer import HarmoniConsumer
    unique_group = f"test-roundtrip-{uuid.uuid4().hex[:8]}"
    return HarmoniConsumer(kafka_config, schema_manager, unique_group, [topic])


def _consume_one(consumer: Any, timeout_total: float = 15.0) -> Any:
    """Poll until we get a message or timeout."""
    start = time.time()
    while time.time() - start < timeout_total:
        msg = consumer.poll(timeout=1.0)
        if msg is not None:
            return msg
    return None


# ---------------------------------------------------------------------------
# Web pageview round-trip
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_web_pageview_roundtrip(kafka_config: Any, schema_manager: Any, producer: Any) -> None:
    from ingestion.connectors.web import WebAnalyticsConnector
    from ingestion.kafka import topics

    connector = WebAnalyticsConnector(producer)
    raw = connector.generate_mock_event()
    domain, normalized = connector.normalize(raw)
    assert domain is not None
    producer.produce(topics.WEB_PAGEVIEW, normalized, domain)
    producer.flush()

    consumer = _make_consumer(schema_manager, kafka_config, topics.WEB_PAGEVIEW)
    with consumer:
        msg = _consume_one(consumer)

    assert msg is not None, "No message consumed within timeout"
    assert msg.value["account_domain"] == domain
    assert "page_url" in msg.value


# ---------------------------------------------------------------------------
# Email engagement round-trip
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_email_engagement_roundtrip(kafka_config: Any, schema_manager: Any, producer: Any) -> None:
    from ingestion.connectors.email import EmailEngagementConnector
    from ingestion.kafka import topics

    connector = EmailEngagementConnector(producer)
    raw = connector.generate_mock_event()
    domain, normalized = connector.normalize(raw)
    assert domain is not None
    producer.produce(topics.EMAIL_ENGAGEMENT, normalized, domain)
    producer.flush()

    consumer = _make_consumer(schema_manager, kafka_config, topics.EMAIL_ENGAGEMENT)
    with consumer:
        msg = _consume_one(consumer)

    assert msg is not None
    assert msg.value["account_domain"] == domain
    assert "engagement_type" in msg.value
    assert isinstance(msg.value["is_negative"], bool)


# ---------------------------------------------------------------------------
# CRM contact activity round-trip
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_crm_activity_roundtrip(kafka_config: Any, schema_manager: Any, producer: Any) -> None:
    from ingestion.connectors.crm import CRMActivityConnector
    from ingestion.kafka import topics

    connector = CRMActivityConnector(producer)
    raw = connector.generate_mock_event()
    domain, normalized = connector.normalize(raw)
    assert domain is not None
    producer.produce(topics.CRM_CONTACT_ACTIVITY, normalized, domain)
    producer.flush()

    consumer = _make_consumer(schema_manager, kafka_config, topics.CRM_CONTACT_ACTIVITY)
    with consumer:
        msg = _consume_one(consumer)

    assert msg is not None
    assert msg.value["account_domain"] == domain
    assert "activity_type" in msg.value


# ---------------------------------------------------------------------------
# Webinar attendance round-trip
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_webinar_attendance_roundtrip(kafka_config: Any, schema_manager: Any, producer: Any) -> None:
    from ingestion.connectors.webinar import WebinarAttendanceConnector
    from ingestion.kafka import topics

    connector = WebinarAttendanceConnector(producer)
    raw = connector.generate_mock_event()
    domain, normalized = connector.normalize(raw)
    assert domain is not None
    producer.produce(topics.WEBINAR_ATTENDANCE, normalized, domain)
    producer.flush()

    consumer = _make_consumer(schema_manager, kafka_config, topics.WEBINAR_ATTENDANCE)
    with consumer:
        msg = _consume_one(consumer)

    assert msg is not None
    assert msg.value["account_domain"] == domain
    assert "attendance_type" in msg.value


# ---------------------------------------------------------------------------
# DLQ routing: Schema Registry rejects unregistered schema
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_dlq_receives_invalid_schema_messages(
    kafka_config: Any, schema_manager: Any, producer: Any
) -> None:
    """Producing a dict that violates the schema should route to DLQ."""
    from ingestion.kafka import topics

    # Produce a dict that is missing required fields for web_pageview
    bad_event = {"totally_wrong_field": "should_fail"}
    producer.produce(topics.WEB_PAGEVIEW, bad_event, account_domain="acme.com")
    producer.flush()

    consumer = _make_consumer(schema_manager, kafka_config, topics.DLQ)
    with consumer:
        msg = _consume_one(consumer)

    assert msg is not None, "Expected a DLQ message for the invalid event"
    assert msg.value["source_topic"] == "harmoni.web.pageview"
    assert msg.value["failure_stage"] in ("SERIALIZATION", "SCHEMA_VALIDATION")
