"""Unit tests for all four source connectors.

Verifies:
- normalize() extracts the correct account_domain
- normalized dicts are schema-compatible (validated with fastavro)
- mock data generators produce valid, schema-conformant events
- free-email domains are quarantined (return None, {})
- ingest() calls producer.produce() with correct topic and domain
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import fastavro
import fastavro.schema
import pytest

from ingestion.connectors.crm import CRMActivityConnector
from ingestion.connectors.email import EmailEngagementConnector
from ingestion.connectors.web import WebAnalyticsConnector
from ingestion.connectors.webinar import WebinarAttendanceConnector
from ingestion.kafka import topics

SCHEMAS_DIR = Path(__file__).parent.parent / "schemas"


def _parse_schema(stem: str) -> Any:
    path = SCHEMAS_DIR / f"{stem}.avsc"
    return fastavro.schema.parse_schema(json.loads(path.read_text()))


def _avro_roundtrip(schema: Any, record: dict[str, Any]) -> dict[str, Any]:
    """Serialize then deserialize to verify schema compatibility."""
    buf = io.BytesIO()
    fastavro.schemaless_writer(buf, schema, record)
    buf.seek(0)
    return fastavro.schemaless_reader(buf, schema)


# ---------------------------------------------------------------------------
# WebAnalyticsConnector
# ---------------------------------------------------------------------------


class TestWebAnalyticsConnector:
    @pytest.fixture
    def connector(self, mock_producer: Any) -> WebAnalyticsConnector:
        return WebAnalyticsConnector(mock_producer)

    @pytest.fixture(scope="class")
    def schema(self) -> Any:
        return _parse_schema("web_pageview")

    @pytest.mark.unit
    def test_normalize_extracts_account_domain(self, connector: WebAnalyticsConnector) -> None:
        raw = {
            "contact_email": "cto@acme.com",
            "page_location": "https://harmoni.io/pricing",
            "session_id": "sess-1",
        }
        domain, normalized = connector.normalize(raw)
        assert domain == "acme.com"
        assert normalized["account_domain"] == "acme.com"

    @pytest.mark.unit
    def test_normalize_classifies_pricing_page(self, connector: WebAnalyticsConnector) -> None:
        raw = {"contact_email": "vp@corp.io", "page_location": "https://harmoni.io/pricing"}
        _, normalized = connector.normalize(raw)
        assert normalized["page_category"] == "PRICING"

    @pytest.mark.unit
    def test_normalize_classifies_demo_page(self, connector: WebAnalyticsConnector) -> None:
        raw = {"contact_email": "vp@corp.io", "page_location": "https://harmoni.io/demo"}
        _, normalized = connector.normalize(raw)
        assert normalized["page_category"] == "DEMO"

    @pytest.mark.unit
    def test_normalize_quarantines_free_email(self, connector: WebAnalyticsConnector) -> None:
        raw = {"contact_email": "personal@gmail.com", "page_location": "/pricing"}
        domain, normalized = connector.normalize(raw)
        assert domain is None
        assert normalized == {}

    @pytest.mark.unit
    def test_normalize_quarantines_missing_email(self, connector: WebAnalyticsConnector) -> None:
        raw = {"page_location": "/pricing"}
        domain, _ = connector.normalize(raw)
        assert domain is None

    @pytest.mark.unit
    def test_mock_event_is_schema_compatible(
        self, connector: WebAnalyticsConnector, schema: Any
    ) -> None:
        raw = connector.generate_mock_event()
        _, normalized = connector.normalize(raw)
        assert normalized
        _avro_roundtrip(schema, normalized)  # raises on schema mismatch

    @pytest.mark.unit
    def test_ingest_calls_producer_with_correct_topic(
        self, connector: WebAnalyticsConnector, mock_producer: Any
    ) -> None:
        raw = {"contact_email": "cfo@acme.com", "page_location": "/pricing"}
        connector.ingest(raw)
        mock_producer.produce.assert_called_once()
        call_topic = mock_producer.produce.call_args[0][0]
        assert call_topic == topics.WEB_PAGEVIEW

    @pytest.mark.unit
    def test_ingest_passes_correct_domain_as_key(
        self, connector: WebAnalyticsConnector, mock_producer: Any
    ) -> None:
        raw = {"contact_email": "cfo@acme.com", "page_location": "/pricing"}
        connector.ingest(raw)
        domain_arg = mock_producer.produce.call_args[1]["account_domain"]
        assert domain_arg == "acme.com"


# ---------------------------------------------------------------------------
# EmailEngagementConnector
# ---------------------------------------------------------------------------


class TestEmailEngagementConnector:
    @pytest.fixture
    def connector(self, mock_producer: Any) -> EmailEngagementConnector:
        return EmailEngagementConnector(mock_producer)

    @pytest.fixture(scope="class")
    def schema(self) -> Any:
        return _parse_schema("email_engagement")

    @pytest.mark.unit
    def test_normalize_maps_open_event(self, connector: EmailEngagementConnector) -> None:
        raw = {"recipient_email": "cto@globex.io", "event_type": "open"}
        domain, normalized = connector.normalize(raw)
        assert domain == "globex.io"
        assert normalized["engagement_type"] == "OPENED"
        assert normalized["is_negative"] is False

    @pytest.mark.unit
    def test_normalize_marks_unsubscribe_as_negative(
        self, connector: EmailEngagementConnector
    ) -> None:
        raw = {"recipient_email": "cto@globex.io", "event_type": "unsubscribe"}
        _, normalized = connector.normalize(raw)
        assert normalized["engagement_type"] == "UNSUBSCRIBED"
        assert normalized["is_negative"] is True

    @pytest.mark.unit
    def test_normalize_marks_bounce_as_negative(self, connector: EmailEngagementConnector) -> None:
        raw = {"recipient_email": "cto@globex.io", "event_type": "bounce"}
        _, normalized = connector.normalize(raw)
        assert normalized["is_negative"] is True

    @pytest.mark.unit
    def test_normalize_marks_spam_report_as_negative(
        self, connector: EmailEngagementConnector
    ) -> None:
        raw = {"recipient_email": "cto@globex.io", "event_type": "spam"}
        _, normalized = connector.normalize(raw)
        assert normalized["is_negative"] is True

    @pytest.mark.unit
    def test_normalize_quarantines_free_email(self, connector: EmailEngagementConnector) -> None:
        raw = {"recipient_email": "x@yahoo.com", "event_type": "open"}
        domain, _ = connector.normalize(raw)
        assert domain is None

    @pytest.mark.unit
    def test_mock_event_is_schema_compatible(
        self, connector: EmailEngagementConnector, schema: Any
    ) -> None:
        raw = connector.generate_mock_event()
        _, normalized = connector.normalize(raw)
        assert normalized
        _avro_roundtrip(schema, normalized)


# ---------------------------------------------------------------------------
# CRMActivityConnector
# ---------------------------------------------------------------------------


class TestCRMActivityConnector:
    @pytest.fixture
    def connector(self, mock_producer: Any) -> CRMActivityConnector:
        return CRMActivityConnector(mock_producer)

    @pytest.fixture(scope="class")
    def schema(self) -> Any:
        return _parse_schema("crm_contact_activity")

    @pytest.mark.unit
    def test_normalize_maps_hubspot_meeting_creation(
        self, connector: CRMActivityConnector
    ) -> None:
        raw = {
            "subscriptionType": "meeting.creation",
            "objectId": 12345,
            "contact_email": "vp@initech.com",
        }
        domain, normalized = connector.normalize(raw)
        assert domain == "initech.com"
        assert normalized["activity_type"] == "MEETING_BOOKED"

    @pytest.mark.unit
    def test_normalize_falls_back_to_company_domain(
        self, connector: CRMActivityConnector
    ) -> None:
        raw = {"company_domain": "hooli.com", "subscriptionType": "deal.creation"}
        domain, normalized = connector.normalize(raw)
        assert domain == "hooli.com"

    @pytest.mark.unit
    def test_normalize_quarantines_missing_domain(
        self, connector: CRMActivityConnector
    ) -> None:
        raw = {"subscriptionType": "contact.creation"}
        domain, _ = connector.normalize(raw)
        assert domain is None

    @pytest.mark.unit
    def test_mock_event_is_schema_compatible(
        self, connector: CRMActivityConnector, schema: Any
    ) -> None:
        raw = connector.generate_mock_event()
        _, normalized = connector.normalize(raw)
        assert normalized
        _avro_roundtrip(schema, normalized)

    @pytest.mark.unit
    def test_ingest_hubspot_batch(
        self, connector: CRMActivityConnector, mock_producer: Any
    ) -> None:
        batch = [connector.generate_mock_event() for _ in range(3)]
        connector.ingest_hubspot_batch(batch)
        assert mock_producer.produce.call_count == 3


# ---------------------------------------------------------------------------
# WebinarAttendanceConnector
# ---------------------------------------------------------------------------


class TestWebinarAttendanceConnector:
    @pytest.fixture
    def connector(self, mock_producer: Any) -> WebinarAttendanceConnector:
        return WebinarAttendanceConnector(mock_producer)

    @pytest.fixture(scope="class")
    def schema(self) -> Any:
        return _parse_schema("webinar_attendance")

    @pytest.mark.unit
    def test_normalize_zoom_registration(self, connector: WebinarAttendanceConnector) -> None:
        raw = {
            "event": "webinar.registration_created",
            "contact_email": "cfo@umbrella.co",
            "webinar_id": "wb-001",
            "webinar_title": "harmoni Live Product Demo",
        }
        domain, normalized = connector.normalize(raw)
        assert domain == "umbrella.co"
        assert normalized["attendance_type"] == "REGISTERED"
        assert normalized["webinar_topic"] == "PRODUCT_DEMO"

    @pytest.mark.unit
    def test_normalize_classifies_product_demo_topic(
        self, connector: WebinarAttendanceConnector
    ) -> None:
        raw = {
            "contact_email": "cto@acme.com",
            "webinar_id": "wb-001",
            "webinar_title": "Product Demo — Q3",
            "event_type": "attendance",
        }
        _, normalized = connector.normalize(raw)
        assert normalized["webinar_topic"] == "PRODUCT_DEMO"

    @pytest.mark.unit
    def test_normalize_classifies_thought_leadership(
        self, connector: WebinarAttendanceConnector
    ) -> None:
        raw = {
            "contact_email": "cto@acme.com",
            "webinar_id": "wb-002",
            "webinar_title": "State of ABM 2026",
            "event_type": "registration",
        }
        _, normalized = connector.normalize(raw)
        assert normalized["webinar_topic"] == "THOUGHT_LEADERSHIP"

    @pytest.mark.unit
    def test_normalize_quarantines_free_email(
        self, connector: WebinarAttendanceConnector
    ) -> None:
        raw = {"contact_email": "user@gmail.com", "webinar_id": "wb-x", "event_type": "attendance"}
        domain, _ = connector.normalize(raw)
        assert domain is None

    @pytest.mark.unit
    def test_mock_event_is_schema_compatible(
        self, connector: WebinarAttendanceConnector, schema: Any
    ) -> None:
        raw = connector.generate_mock_event()
        _, normalized = connector.normalize(raw)
        assert normalized
        _avro_roundtrip(schema, normalized)
