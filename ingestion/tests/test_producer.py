"""Unit tests for HarmoniProducer.

Tests use mock confluent-kafka Producer and mock SchemaRegistryManager.
No live Kafka or Schema Registry required.
"""

from __future__ import annotations

import struct
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest

from ingestion.kafka import topics
from ingestion.kafka.producer import HarmoniProducer, _now_ms, _safe_json_bytes
from ingestion.tests.conftest import make_mock_schema_manager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_confluent_producer() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_kafka_config() -> MagicMock:
    cfg = MagicMock()
    cfg.base_producer_config.return_value = {"bootstrap.servers": "localhost:9092"}
    return cfg


@pytest.fixture
def producer(mock_kafka_config: MagicMock, mock_confluent_producer: MagicMock) -> HarmoniProducer:
    mgr = make_mock_schema_manager()
    with patch("ingestion.kafka.producer.Producer", return_value=mock_confluent_producer):
        p = HarmoniProducer(mock_kafka_config, mgr)
    return p


# ---------------------------------------------------------------------------
# produce() — happy path
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_produce_calls_underlying_producer(
    producer: HarmoniProducer,
    mock_confluent_producer: MagicMock,
) -> None:
    event = {
        "event_id": "abc",
        "account_domain": "acme.com",
        "session_id": "sess1",
        "page_url": "https://harmoni.io/pricing",
        "page_category": "PRICING",
        "occurred_at": _now_ms(),
        "ingested_at": _now_ms(),
    }
    producer.produce(topics.WEB_PAGEVIEW, event, account_domain="acme.com")
    mock_confluent_producer.produce.assert_called_once()
    call_kwargs = mock_confluent_producer.produce.call_args[1]
    assert call_kwargs["topic"] == "harmoni.web.pageview"
    assert call_kwargs["key"] == b"acme.com"


@pytest.mark.unit
def test_produce_key_is_utf8_encoded_domain(
    producer: HarmoniProducer,
    mock_confluent_producer: MagicMock,
) -> None:
    event = {"event_id": "x", "account_domain": "acme.com", "page_url": "/", "session_id": "s",
             "page_category": "OTHER", "occurred_at": _now_ms(), "ingested_at": _now_ms()}
    producer.produce(topics.WEB_PAGEVIEW, event, account_domain="acme.com")
    key_arg = mock_confluent_producer.produce.call_args[1]["key"]
    assert key_arg == b"acme.com"
    assert isinstance(key_arg, bytes)


# ---------------------------------------------------------------------------
# produce() — DLQ routing on serialization failure
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_serialization_failure_routes_to_dlq(
    mock_kafka_config: MagicMock,
    mock_confluent_producer: MagicMock,
) -> None:
    """When serialize() raises, the message is routed to DLQ."""
    failing_mgr = MagicMock()
    failing_mgr.serialize.side_effect = ValueError("bad schema")

    with patch("ingestion.kafka.producer.Producer", return_value=mock_confluent_producer):
        p = HarmoniProducer(mock_kafka_config, failing_mgr)

    p.produce(topics.WEB_PAGEVIEW, {"bad": "event"}, account_domain="acme.com")

    # serialize called twice: once for original topic (fails), once for DLQ
    assert failing_mgr.serialize.call_count == 2
    dlq_call = failing_mgr.serialize.call_args_list[1]
    assert dlq_call[0][0] == "harmoni.dlq-value"


@pytest.mark.unit
def test_dlq_envelope_contains_error_details(
    mock_kafka_config: MagicMock,
    mock_confluent_producer: MagicMock,
) -> None:
    """DLQ envelope has correct source_topic and error info."""
    captured_envelopes: list[dict[str, Any]] = []

    def capture_serialize(subject: str, value: dict[str, Any]) -> bytes:
        if subject == "harmoni.dlq-value":
            captured_envelopes.append(value)
            return b"\x00\x00\x00\x00\x01dlq"
        raise ValueError("intentional test failure")

    mgr = MagicMock()
    mgr.serialize.side_effect = capture_serialize

    with patch("ingestion.kafka.producer.Producer", return_value=mock_confluent_producer):
        p = HarmoniProducer(mock_kafka_config, mgr)

    p.produce(topics.WEB_PAGEVIEW, {"x": 1}, account_domain="acme.com")

    assert len(captured_envelopes) == 1
    env = captured_envelopes[0]
    assert env["source_topic"] == "harmoni.web.pageview"
    assert env["error_class"] == "ValueError"
    assert "intentional test failure" in env["error_message"]
    assert env["failure_stage"] == "SERIALIZATION"


@pytest.mark.unit
def test_dlq_produce_failure_logs_but_does_not_raise(
    mock_kafka_config: MagicMock,
    mock_confluent_producer: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """If even the DLQ produce fails, we log CRITICAL but do not raise."""
    mgr = MagicMock()
    mgr.serialize.side_effect = RuntimeError("total failure")

    with patch("ingestion.kafka.producer.Producer", return_value=mock_confluent_producer):
        p = HarmoniProducer(mock_kafka_config, mgr)

    import logging
    with caplog.at_level(logging.ERROR, logger="ingestion.kafka.producer"):
        p.produce(topics.WEB_PAGEVIEW, {}, account_domain="acme.com")  # must not raise

    assert any("CRITICAL" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# flush()
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_flush_delegates_to_confluent_producer(
    producer: HarmoniProducer,
    mock_confluent_producer: MagicMock,
) -> None:
    mock_confluent_producer.flush.return_value = 0
    remaining = producer.flush(timeout=5.0)
    mock_confluent_producer.flush.assert_called_once_with(5.0)
    assert remaining == 0


@pytest.mark.unit
def test_context_manager_flushes_on_exit(
    mock_kafka_config: MagicMock,
    mock_confluent_producer: MagicMock,
) -> None:
    mgr = make_mock_schema_manager()
    with patch("ingestion.kafka.producer.Producer", return_value=mock_confluent_producer):
        with HarmoniProducer(mock_kafka_config, mgr):
            pass
    mock_confluent_producer.flush.assert_called()


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_safe_json_bytes_handles_non_serializable() -> None:
    value: dict[str, Any] = {"dt": object()}  # non-JSON-serializable
    result = _safe_json_bytes(value)
    assert isinstance(result, bytes)
    assert len(result) > 0


@pytest.mark.unit
def test_now_ms_returns_positive_int() -> None:
    ts = _now_ms()
    assert isinstance(ts, int)
    assert ts > 0
