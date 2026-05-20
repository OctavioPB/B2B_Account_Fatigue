"""Webinar Attendance Connector.

Ingests Zoom and GoToWebinar webhook payloads and produces to
harmoni.webinar.attendance.

Webinar events are among the strongest intent signals in the pipeline:
- ATTENDED_LIVE is weighted 3× higher than REGISTERED
- questions_asked is the single strongest individual webinar signal
- PRODUCT_DEMO topic triggers immediate NBA evaluation

Reference (Zoom webhooks): https://developers.zoom.us/docs/api/webhooks/
"""

from __future__ import annotations

import random
from typing import Any

from faker import Faker

from ingestion.connectors.base import BaseConnector
from ingestion.kafka.topics import WEBINAR_ATTENDANCE, TopicConfig

_fake = Faker()

# Zoom event → canonical AttendanceType
_ZOOM_EVENT_MAP: dict[str, str] = {
    "webinar.registration_created": "REGISTERED",
    "webinar.participant_joined":   "ATTENDED_LIVE",
    "webinar.participant_left":     "ATTENDED_LIVE",
    "webinar.ended":                "ATTENDED_LIVE",
    # GoToWebinar
    "REGISTRANT_ADDED":             "REGISTERED",
    "ATTENDANCE_RECORDED":          "ATTENDED_LIVE",
    # Generic
    "registration":                 "REGISTERED",
    "attendance":                   "ATTENDED_LIVE",
    "recording_view":               "WATCHED_RECORDING",
    "no_show":                      "NO_SHOW",
}

# Title keywords → WebinarTopic classification
_TOPIC_KEYWORDS: list[tuple[str, str]] = [
    ("demo",        "PRODUCT_DEMO"),
    ("product",     "PRODUCT_DEMO"),
    ("tour",        "PRODUCT_DEMO"),
    ("technical",   "TECHNICAL"),
    ("engineering", "TECHNICAL"),
    ("api",         "TECHNICAL"),
    ("case study",  "CUSTOMER_STORY"),
    ("customer",    "CUSTOMER_STORY"),
    ("thought",     "THOUGHT_LEADERSHIP"),
    ("trend",       "THOUGHT_LEADERSHIP"),
    ("state of",    "THOUGHT_LEADERSHIP"),
]

_MOCK_COMPANY_DOMAINS = [
    "acme-corp.com", "globex.io", "initech.com", "hooli.com",
    "pied-piper.com", "umbrella.co", "cyberdyne.io",
]

_MOCK_WEBINARS: list[tuple[str, str]] = [
    ("harmoni-live-demo-q3", "harmoni Live Product Demo"),
    ("state-of-abm-2026",    "State of ABM 2026: Committee Fatigue Report"),
    ("rev-intel-masterclass", "Revenue Intelligence Masterclass"),
    ("customer-story-series", "Customer Story: 3× Pipeline Velocity"),
    ("technical-deep-dive",   "Technical Deep Dive: Intent Network Modeling"),
]

_MOCK_TITLES = [
    "VP of Revenue Operations", "Chief Marketing Officer",
    "Director of Demand Generation", "Head of Sales Development",
    "Chief Technology Officer", "VP of Finance",
]


def _classify_webinar_topic(title: str) -> str:
    title_lower = title.lower()
    for keyword, topic in _TOPIC_KEYWORDS:
        if keyword in title_lower:
            return topic
    return "OTHER"


class WebinarAttendanceConnector(BaseConnector):
    """Ingests webinar registration and attendance events."""

    @property
    def topic(self) -> TopicConfig:
        return WEBINAR_ATTENDANCE

    def normalize(
        self, raw_event: dict[str, Any]
    ) -> tuple[str | None, dict[str, Any]]:
        """Normalize a Zoom / GoToWebinar webhook to WebinarAttendance schema.

        Zoom payload keys (under payload.object.registrant or attendee):
            event, payload.object.uuid, payload.object.topic,
            payload.object.registrant.email, first_name, last_name, job_title

        Generic keys (normalized prior or passed directly):
            contact_email, contact_first_name, contact_last_name,
            contact_title, webinar_id, webinar_title, event_type,
            duration_minutes, questions_asked, polls_answered, platform
        """
        # Support both nested Zoom format and flat format
        payload_obj = raw_event.get("payload", {}).get("object", {})
        registrant = payload_obj.get("registrant") or payload_obj.get("attendee") or {}

        contact_email = (
            raw_event.get("contact_email")
            or registrant.get("email", "")
        )
        account_domain = self._resolve_domain(contact_email)
        if account_domain is None:
            return None, {}

        raw_event_type = raw_event.get("event") or raw_event.get("event_type", "")
        attendance_type = _ZOOM_EVENT_MAP.get(raw_event_type, "REGISTERED")

        webinar_title = (
            raw_event.get("webinar_title")
            or payload_obj.get("topic", "")
        )

        normalized: dict[str, Any] = {
            "event_id":                   self._new_event_id(),
            "account_domain":             account_domain,
            "contact_email":              contact_email,
            "contact_first_name":         (
                raw_event.get("contact_first_name")
                or registrant.get("first_name")
            ),
            "contact_last_name":          (
                raw_event.get("contact_last_name")
                or registrant.get("last_name")
            ),
            "contact_title":              (
                raw_event.get("contact_title")
                or registrant.get("job_title")
            ),
            "webinar_id":                 (
                raw_event.get("webinar_id")
                or payload_obj.get("uuid", self._new_event_id())
            ),
            "webinar_title":              webinar_title or "Unknown Webinar",
            "webinar_topic":              _classify_webinar_topic(webinar_title),
            "attendance_type":            attendance_type,
            "attendance_duration_minutes": (
                raw_event.get("duration_minutes")
                or raw_event.get("attendance_duration_minutes")
            ),
            "questions_asked":            int(raw_event.get("questions_asked", 0)),
            "polls_answered":             int(raw_event.get("polls_answered", 0)),
            "platform":                   raw_event.get("platform", "OTHER"),
            "occurred_at":                raw_event.get("occurred_at") or self._now_ms(),
            "ingested_at":                self._now_ms(),
        }
        return account_domain, normalized

    def generate_mock_event(self) -> dict[str, Any]:
        """Generate a realistic webinar attendance event."""
        domain = random.choice(_MOCK_COMPANY_DOMAINS)
        webinar_id, webinar_title = random.choice(_MOCK_WEBINARS)
        first, last = _fake.first_name(), _fake.last_name()
        attended = random.random() > 0.3
        return {
            "event":            "webinar.participant_joined" if attended else "webinar.registration_created",
            "event_type":       "attendance" if attended else "registration",
            "contact_email":    f"{first.lower()}.{last.lower()}@{domain}",
            "contact_first_name": first,
            "contact_last_name":  last,
            "contact_title":    random.choice(_MOCK_TITLES),
            "webinar_id":       webinar_id,
            "webinar_title":    webinar_title,
            "attendance_type":  "ATTENDED_LIVE" if attended else "REGISTERED",
            "duration_minutes": random.randint(15, 60) if attended else None,
            "questions_asked":  random.randint(0, 3) if attended else 0,
            "polls_answered":   random.randint(0, 2) if attended else 0,
            "platform":         random.choice(["ZOOM", "GOTOWEBINAR", "ON24"]),
            "occurred_at":      self._now_ms() - random.randint(0, 7 * 86_400_000),
        }
