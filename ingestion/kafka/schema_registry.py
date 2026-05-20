"""Schema Registry manager — loads, registers, and caches Avro schemas.

Handles:
- Loading all .avsc files from ingestion/schemas/
- Registering schemas with Confluent Schema Registry
- Caching parsed schemas and schema IDs for serialization
- Confluent wire format serialization / deserialization

Wire format (Confluent):
    byte 0:     magic byte 0x00
    bytes 1-4:  schema ID (big-endian int32)
    bytes 5+:   fastavro schemaless-encoded message
"""

from __future__ import annotations

import io
import json
import logging
import struct
from pathlib import Path
from typing import Any

import fastavro
import fastavro.schema
from confluent_kafka.schema_registry import Schema, SchemaRegistryClient

logger = logging.getLogger(__name__)

_MAGIC_BYTE = b"\x00"
_SCHEMAS_DIR = Path(__file__).parent.parent / "schemas"

# subject → schema file stem mapping (TopicNameStrategy)
_SUBJECT_TO_FILE: dict[str, str] = {
    "harmoni.dlq-value":                   "dlq_envelope",
    "harmoni.web.pageview-value":           "web_pageview",
    "harmoni.email.engagement-value":       "email_engagement",
    "harmoni.crm.contact_activity-value":   "crm_contact_activity",
    "harmoni.webinar.attendance-value":     "webinar_attendance",
    "harmoni.intent_signal-value":          "intent_signal",
}


class SchemaRegistryManager:
    """Manages schema registration and caching for the harmoni pipeline.

    Call `register_all()` once at service startup. After that, `serialize()`
    and `deserialize()` are safe to call from any thread (cache is read-only
    after initialization).
    """

    def __init__(self, schema_registry_url: str) -> None:
        self._client = SchemaRegistryClient({"url": schema_registry_url})
        # subject → (parsed_schema_dict, schema_id)
        self._cache: dict[str, tuple[Any, int]] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_all(
        self,
        schemas_dir: Path = _SCHEMAS_DIR,
        compatibility: str = "BACKWARD",
    ) -> dict[str, int]:
        """Register all .avsc schemas and return subject → schema_id mapping.

        DLQ schema is always registered first per ADR 0003.
        Safe to call multiple times (idempotent — re-registration returns existing ID).
        """
        # DLQ first
        results: dict[str, int] = {}
        dlq_subject = "harmoni.dlq-value"
        results[dlq_subject] = self._register_subject(dlq_subject, schemas_dir)

        for subject, stem in _SUBJECT_TO_FILE.items():
            if subject == dlq_subject:
                continue
            results[subject] = self._register_subject(subject, schemas_dir)

        logger.info("Registered %d schemas with Schema Registry.", len(results))
        return results

    def _register_subject(self, subject: str, schemas_dir: Path) -> int:
        stem = _SUBJECT_TO_FILE[subject]
        schema_path = schemas_dir / f"{stem}.avsc"
        schema_str = schema_path.read_text(encoding="utf-8")

        schema = Schema(schema_str, schema_type="AVRO")
        schema_id = self._client.register_schema(subject, schema)

        parsed = fastavro.schema.parse_schema(json.loads(schema_str))
        self._cache[subject] = (parsed, schema_id)
        logger.debug("Registered subject=%s schema_id=%d", subject, schema_id)
        return schema_id

    # ------------------------------------------------------------------
    # Lazy loading (for consumers that don't call register_all)
    # ------------------------------------------------------------------

    def _load_subject(self, subject: str) -> tuple[Any, int]:
        if subject in self._cache:
            return self._cache[subject]

        registered = self._client.get_latest_version(subject)
        parsed = fastavro.schema.parse_schema(
            json.loads(registered.schema.schema_str)
        )
        self._cache[subject] = (parsed, registered.schema_id)
        return self._cache[subject]

    def _load_by_id(self, schema_id: int) -> Any:
        """Load and parse schema by numeric ID (used during deserialization)."""
        schema_obj = self._client.get_schema(schema_id)
        return fastavro.schema.parse_schema(json.loads(schema_obj.schema_str))

    # ------------------------------------------------------------------
    # Serialization / deserialization
    # ------------------------------------------------------------------

    def serialize(self, subject: str, value: dict[str, Any]) -> bytes:
        """Serialize *value* to Confluent Avro wire format.

        Args:
            subject: Schema Registry subject (e.g. "harmoni.web.pageview-value").
            value:   Dict matching the subject's Avro schema.

        Returns:
            Bytes in Confluent wire format (magic + schema_id + avro).

        Raises:
            ValueError: If *subject* is not registered.
            fastavro.write.ValidationError: If *value* does not match schema.
        """
        schema, schema_id = self._load_subject(subject)
        buf = io.BytesIO()
        buf.write(_MAGIC_BYTE)
        buf.write(struct.pack(">I", schema_id))
        fastavro.schemaless_writer(buf, schema, value)
        return buf.getvalue()

    def deserialize(self, data: bytes) -> dict[str, Any]:
        """Deserialize Confluent Avro wire-format bytes to a dict.

        Raises:
            ValueError: If magic byte is invalid.
        """
        if not data or data[0:1] != _MAGIC_BYTE:
            raise ValueError(
                f"Invalid Confluent magic byte: {data[0:1]!r}. Expected 0x00."
            )
        schema_id = struct.unpack(">I", data[1:5])[0]
        schema = self._load_by_id(schema_id)
        buf = io.BytesIO(data[5:])
        return fastavro.schemaless_reader(buf, schema)  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def get_schema_id(self, subject: str) -> int:
        _, schema_id = self._load_subject(subject)
        return schema_id

    def load_schema_file(self, stem: str, schemas_dir: Path = _SCHEMAS_DIR) -> dict[str, Any]:
        """Return the parsed schema dict for a given file stem (no registry call)."""
        path = schemas_dir / f"{stem}.avsc"
        return fastavro.schema.parse_schema(json.loads(path.read_text(encoding="utf-8")))
