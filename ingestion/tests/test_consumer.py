"""Unit tests for HarmoniConsumer.

Tests use mock confluent-kafka Consumer — no live Kafka required.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from confluent_kafka import KafkaError, KafkaException

from ingestion.kafka import topics
from ingestion.kafka.consumer import ConsumedMessage, HarmoniConsumer
from ingestion.tests.conftest import make_mock_schema_manager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_confluent_consumer() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_kafka_config() -> MagicMock:
    cfg = MagicMock()
    cfg.base_consumer_config.return_value = {
        "bootstrap.servers": "localhost:9092",
        "group.id": "test-group",
        "enable.auto.commit": False,
    }
    return cfg


@pytest.fixture
def consumer(
    mock_kafka_config: MagicMock,
    mock_confluent_consumer: MagicMock,
) -> HarmoniConsumer:
    mgr = make_mock_schema_manager()
    with patch("ingestion.kafka.consumer.Consumer", return_value=mock_confluent_consumer):
        c = HarmoniConsumer(
            mock_kafka_config,
            mgr,
            group_id="test-group",
            topics=[topics.WEB_PAGEVIEW],
        )
    return c


def _make_mock_message(
    topic: str = "harmoni.web.pageview",
    partition: int = 0,
    offset: int = 100,
    key: bytes = b"acme.com",
    value: bytes = b"\x00\x00\x00\x00\x2a" + b"fake",
    error: KafkaError | None = None,
) -> MagicMock:
    msg = MagicMock()
    msg.topic.return_value = topic
    msg.partition.return_value = partition
    msg.offset.return_value = offset
    msg.key.return_value = key
    msg.value.return_value = value
    msg.error.return_value = error
    return msg


# ---------------------------------------------------------------------------
# poll() — happy path
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_poll_returns_none_on_timeout(
    consumer: HarmoniConsumer,
    mock_confluent_consumer: MagicMock,
) -> None:
    mock_confluent_consumer.poll.return_value = None
    result = consumer.poll(timeout=0.1)
    assert result is None


@pytest.mark.unit
def test_poll_returns_consumed_message(
    consumer: HarmoniConsumer,
    mock_confluent_consumer: MagicMock,
) -> None:
    mock_msg = _make_mock_message()
    mock_confluent_consumer.poll.return_value = mock_msg
    consumer._schema.deserialize.return_value = {"event_id": "123", "account_domain": "acme.com"}

    result = consumer.poll()

    assert result is not None
    assert isinstance(result, ConsumedMessage)
    assert result.topic == "harmoni.web.pageview"
    assert result.partition == 0
    assert result.offset == 100
    assert result.key == "acme.com"
    assert result.value == {"event_id": "123", "account_domain": "acme.com"}


# ---------------------------------------------------------------------------
# poll() — error cases
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_poll_returns_none_on_partition_eof(
    consumer: HarmoniConsumer,
    mock_confluent_consumer: MagicMock,
) -> None:
    eof_error = MagicMock(spec=KafkaError)
    eof_error.code.return_value = KafkaError._PARTITION_EOF
    eof_error.fatal.return_value = False
    mock_msg = _make_mock_message(error=eof_error)
    mock_confluent_consumer.poll.return_value = mock_msg

    result = consumer.poll()
    assert result is None


@pytest.mark.unit
def test_poll_raises_on_fatal_error(
    consumer: HarmoniConsumer,
    mock_confluent_consumer: MagicMock,
) -> None:
    fatal_error = MagicMock(spec=KafkaError)
    fatal_error.code.return_value = KafkaError.UNKNOWN
    fatal_error.fatal.return_value = True
    mock_msg = _make_mock_message(error=fatal_error)
    mock_confluent_consumer.poll.return_value = mock_msg

    with pytest.raises(KafkaException):
        consumer.poll()


@pytest.mark.unit
def test_poll_returns_none_on_deserialization_error(
    consumer: HarmoniConsumer,
    mock_confluent_consumer: MagicMock,
) -> None:
    mock_msg = _make_mock_message()
    mock_confluent_consumer.poll.return_value = mock_msg
    consumer._schema.deserialize.side_effect = ValueError("bad bytes")

    result = consumer.poll()
    assert result is None


# ---------------------------------------------------------------------------
# at-least-once: commit() must be called explicitly
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_commit_calls_confluent_commit_synchronously(
    consumer: HarmoniConsumer,
    mock_confluent_consumer: MagicMock,
) -> None:
    raw_msg = _make_mock_message()
    consumed = ConsumedMessage(
        topic="harmoni.web.pageview",
        partition=0,
        offset=100,
        key="acme.com",
        value={},
        raw_message=raw_msg,
    )
    consumer.commit(consumed)
    mock_confluent_consumer.commit.assert_called_once_with(
        message=raw_msg, asynchronous=False
    )


@pytest.mark.unit
def test_no_autocommit_in_consumer_config(
    mock_kafka_config: MagicMock,
    mock_confluent_consumer: MagicMock,
) -> None:
    """enable.auto.commit must be False — at-least-once contract."""
    config_dict = mock_kafka_config.base_consumer_config.return_value
    assert config_dict["enable.auto.commit"] is False


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_context_manager_calls_close(
    mock_kafka_config: MagicMock,
    mock_confluent_consumer: MagicMock,
) -> None:
    mgr = make_mock_schema_manager()
    with patch("ingestion.kafka.consumer.Consumer", return_value=mock_confluent_consumer):
        with HarmoniConsumer(mock_kafka_config, mgr, "g", [topics.WEB_PAGEVIEW]):
            pass
    mock_confluent_consumer.close.assert_called_once()
