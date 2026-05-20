"""Shared fixtures for ingestion unit tests.

All fixtures in this file use mocks — no live Kafka or Schema Registry
required. Integration tests that need live services are marked
@pytest.mark.integration and live in tests/smoke/.
"""

from __future__ import annotations

import io
import json
import struct
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import fastavro
import fastavro.schema
import pytest

SCHEMAS_DIR = Path(__file__).parent.parent / "schemas"


# ---------------------------------------------------------------------------
# Schema fixtures
# ---------------------------------------------------------------------------


def _load_avsc(stem: str) -> dict[str, Any]:
    path = SCHEMAS_DIR / f"{stem}.avsc"
    return fastavro.schema.parse_schema(json.loads(path.read_text()))


@pytest.fixture(scope="session")
def web_pageview_schema() -> dict[str, Any]:
    return _load_avsc("web_pageview")


@pytest.fixture(scope="session")
def email_engagement_schema() -> dict[str, Any]:
    return _load_avsc("email_engagement")


@pytest.fixture(scope="session")
def crm_contact_activity_schema() -> dict[str, Any]:
    return _load_avsc("crm_contact_activity")


@pytest.fixture(scope="session")
def webinar_attendance_schema() -> dict[str, Any]:
    return _load_avsc("webinar_attendance")


@pytest.fixture(scope="session")
def dlq_envelope_schema() -> dict[str, Any]:
    return _load_avsc("dlq_envelope")


# ---------------------------------------------------------------------------
# Mock SchemaRegistryManager
# ---------------------------------------------------------------------------


def make_mock_schema_manager(schema_id: int = 42) -> MagicMock:
    """Return a mock SchemaRegistryManager that serializes/deserializes in-memory."""
    mgr = MagicMock()

    def fake_serialize(subject: str, value: dict[str, Any]) -> bytes:
        stem = subject.replace("-value", "").split(".")[-1]
        # Map subject to schema file
        subject_to_stem = {
            "harmoni.dlq-value":                  "dlq_envelope",
            "harmoni.web.pageview-value":          "web_pageview",
            "harmoni.email.engagement-value":      "email_engagement",
            "harmoni.crm.contact_activity-value":  "crm_contact_activity",
            "harmoni.webinar.attendance-value":     "webinar_attendance",
        }
        real_stem = subject_to_stem.get(subject, stem)
        schema = _load_avsc(real_stem)
        buf = io.BytesIO()
        buf.write(b"\x00")
        buf.write(struct.pack(">I", schema_id))
        fastavro.schemaless_writer(buf, schema, value)
        return buf.getvalue()

    def fake_deserialize(data: bytes) -> dict[str, Any]:
        # We need the schema to deserialize — for tests, use the subject from context
        # Simplified: just return a fake dict
        return {"deserialized": True}

    mgr.serialize.side_effect = fake_serialize
    mgr.deserialize.side_effect = fake_deserialize
    return mgr


@pytest.fixture
def mock_schema_manager() -> MagicMock:
    return make_mock_schema_manager()


# ---------------------------------------------------------------------------
# Mock HarmoniProducer
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_producer() -> MagicMock:
    """Return a mock HarmoniProducer that captures produce() calls."""
    producer = MagicMock()
    producer.produced_messages: list[dict[str, Any]] = []

    def capture_produce(topic: Any, value: dict, account_domain: str) -> None:
        producer.produced_messages.append(
            {"topic": topic, "value": value, "account_domain": account_domain}
        )

    producer.produce.side_effect = capture_produce
    return producer
