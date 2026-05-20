"""Unit tests for SchemaRegistryManager (offline — no live registry).

Tests wire-format correctness, schema loading, and serialize/deserialize
round-trips using fastavro directly (no network calls).
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

from ingestion.kafka.schema_registry import SchemaRegistryManager, _MAGIC_BYTE

SCHEMAS_DIR = Path(__file__).parent.parent / "schemas"


def _parse(stem: str) -> Any:
    path = SCHEMAS_DIR / f"{stem}.avsc"
    return fastavro.schema.parse_schema(json.loads(path.read_text()))


# ---------------------------------------------------------------------------
# Wire format correctness
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_serialize_starts_with_magic_byte() -> None:
    mgr = SchemaRegistryManager.__new__(SchemaRegistryManager)
    schema = _parse("web_pageview")
    schema_id = 99
    mgr._cache = {"harmoni.web.pageview-value": (schema, schema_id)}

    record = {
        "event_id": "e1", "account_domain": "acme.com", "session_id": "s1",
        "page_url": "/pricing", "page_category": "PRICING",
        "page_title": None, "referrer_url": None, "utm_source": None,
        "utm_medium": None, "utm_campaign": None, "ip_address": None,
        "user_agent": None, "time_on_page_seconds": None,
        "occurred_at": 1_700_000_000_000, "ingested_at": 1_700_000_000_000,
    }
    result = mgr.serialize("harmoni.web.pageview-value", record)
    assert result[0:1] == _MAGIC_BYTE


@pytest.mark.unit
def test_serialize_encodes_schema_id_big_endian() -> None:
    mgr = SchemaRegistryManager.__new__(SchemaRegistryManager)
    schema = _parse("web_pageview")
    schema_id = 42
    mgr._cache = {"harmoni.web.pageview-value": (schema, schema_id)}

    record = {
        "event_id": "e1", "account_domain": "acme.com", "session_id": "s1",
        "page_url": "/pricing", "page_category": "PRICING",
        "page_title": None, "referrer_url": None, "utm_source": None,
        "utm_medium": None, "utm_campaign": None, "ip_address": None,
        "user_agent": None, "time_on_page_seconds": None,
        "occurred_at": 1_700_000_000_000, "ingested_at": 1_700_000_000_000,
    }
    result = mgr.serialize("harmoni.web.pageview-value", record)
    decoded_id = struct.unpack(">I", result[1:5])[0]
    assert decoded_id == 42


@pytest.mark.unit
def test_deserialize_raises_on_invalid_magic_byte() -> None:
    mgr = SchemaRegistryManager.__new__(SchemaRegistryManager)
    mgr._cache = {}
    bad_data = b"\xFF" + b"\x00" * 10
    with pytest.raises(ValueError, match="magic byte"):
        mgr.deserialize(bad_data)


# ---------------------------------------------------------------------------
# Avro schema validation — all .avsc files parse cleanly
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("stem", [
    "intent_signal",
    "web_pageview",
    "email_engagement",
    "crm_contact_activity",
    "webinar_attendance",
    "dlq_envelope",
])
def test_all_avsc_files_parse_without_error(stem: str) -> None:
    schema = _parse(stem)
    assert schema is not None


# ---------------------------------------------------------------------------
# DLQ envelope schema — field presence
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_dlq_envelope_has_required_fields() -> None:
    path = SCHEMAS_DIR / "dlq_envelope.avsc"
    raw = json.loads(path.read_text())
    field_names = {f["name"] for f in raw["fields"]}
    required = {"envelope_id", "source_topic", "error_class", "error_message",
                "original_value", "failure_stage", "failed_at"}
    assert required.issubset(field_names)


# ---------------------------------------------------------------------------
# IntentSignal schema — field presence and enum values
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_intent_signal_source_system_enum_values() -> None:
    path = SCHEMAS_DIR / "intent_signal.avsc"
    raw = json.loads(path.read_text())
    source_field = next(f for f in raw["fields"] if f["name"] == "source_system")
    symbols = source_field["type"]["symbols"]
    assert "WEB" in symbols
    assert "EMAIL" in symbols
    assert "CRM" in symbols
    assert "WEBINAR" in symbols


@pytest.mark.unit
def test_intent_signal_properties_is_map_of_strings() -> None:
    path = SCHEMAS_DIR / "intent_signal.avsc"
    raw = json.loads(path.read_text())
    props_field = next(f for f in raw["fields"] if f["name"] == "properties")
    assert props_field["type"]["type"] == "map"
    assert props_field["type"]["values"] == "string"
    assert props_field["default"] == {}
