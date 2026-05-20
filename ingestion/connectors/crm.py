"""CRM Activity Connector.

Ingests HubSpot (and optionally Salesforce) webhook payloads and produces
to harmoni.crm.contact_activity.

HubSpot webhooks arrive as a list of subscription event objects. This connector
handles both the standard subscription format and the simpler single-event format.

Reference: https://developers.hubspot.com/docs/api/webhooks
"""

from __future__ import annotations

import random
from typing import Any

from faker import Faker

from ingestion.connectors.base import BaseConnector
from ingestion.kafka.topics import CRM_CONTACT_ACTIVITY, TopicConfig

_fake = Faker()

# HubSpot subscriptionType → canonical CRMActivityType
_HUBSPOT_TYPE_MAP: dict[str, str] = {
    "contact.creation":           "CONTACT_CREATED",
    "contact.propertyChange":     "PROPERTY_CHANGED",
    "contact.deletion":           "CONTACT_UPDATED",
    "deal.creation":              "DEAL_CREATED",
    "deal.propertyChange":        "DEAL_STAGE_CHANGED",
    "deal.deletion":              "DEAL_STAGE_CHANGED",
    "meeting.creation":           "MEETING_BOOKED",
    "meeting.completion":         "MEETING_COMPLETED",
    "call.creation":              "CALL_LOGGED",
    "note.creation":              "NOTE_CREATED",
    "task.creation":              "TASK_CREATED",
    "task.completion":            "TASK_COMPLETED",
}

_MOCK_COMPANY_DOMAINS = [
    "acme-corp.com", "globex.io", "initech.com", "hooli.com",
    "pied-piper.com", "umbrella.co", "stark-industries.com",
]

_MOCK_TITLES = [
    "Chief Financial Officer", "Chief Technology Officer", "VP of Revenue",
    "Director of Operations", "Head of Procurement", "VP Engineering",
]

_MOCK_DEAL_STAGES = [
    "Prospecting", "Qualification", "Demo Scheduled",
    "Proposal Sent", "Negotiation", "Closed Won", "Closed Lost",
]


class CRMActivityConnector(BaseConnector):
    """Ingests CRM contact activity from HubSpot / Salesforce webhooks."""

    @property
    def topic(self) -> TopicConfig:
        return CRM_CONTACT_ACTIVITY

    def ingest_hubspot_batch(self, webhook_payload: list[dict[str, Any]]) -> None:
        """Ingest a HubSpot webhook batch (list of subscription events)."""
        for event in webhook_payload:
            self.ingest(event)

    def normalize(
        self, raw_event: dict[str, Any]
    ) -> tuple[str | None, dict[str, Any]]:
        """Normalize a HubSpot (or generic CRM) webhook event.

        HubSpot format keys:
            subscriptionType, objectId, portalId, occurredAt,
            propertyName, propertyValue, changeSource, attemptNumber

        Enriched keys (added by identity resolution layer):
            contact_email, contact_title, company_domain, deal_id, deal_stage
        """
        # Identity resolution must supply contact_email
        contact_email = raw_event.get("contact_email", "")
        account_domain = self._resolve_domain(contact_email)

        # Fall back to explicit company_domain field
        if account_domain is None:
            company_domain = raw_event.get("company_domain", "")
            if company_domain:
                from identity.resolver import normalize_domain, is_free_email_domain
                nd = normalize_domain(company_domain)
                account_domain = None if is_free_email_domain(nd) else nd

        if account_domain is None:
            return None, {}

        raw_type = raw_event.get("subscriptionType") or raw_event.get("activity_type", "")
        activity_type = _HUBSPOT_TYPE_MAP.get(raw_type, "PROPERTY_CHANGED")

        # Flatten raw payload for auditability (all values as strings)
        raw_payload = {k: str(v) for k, v in raw_event.items() if v is not None}

        normalized: dict[str, Any] = {
            "event_id":        self._new_event_id(),
            "account_domain":  account_domain,
            "contact_email":   contact_email,
            "crm_contact_id":  str(raw_event.get("objectId") or raw_event.get("contact_id", "")),
            "crm_company_id":  str(raw_event.get("portalId") or raw_event.get("company_id", ""))
                               or None,
            "crm_source":      raw_event.get("crm_source", "HUBSPOT"),
            "activity_type":   activity_type,
            "deal_id":         raw_event.get("deal_id"),
            "deal_stage":      raw_event.get("deal_stage") or raw_event.get("propertyValue"),
            "deal_value_usd":  raw_event.get("deal_value_usd"),
            "property_name":   raw_event.get("propertyName"),
            "property_value":  raw_event.get("propertyValue"),
            "raw_payload":     raw_payload,
            "occurred_at":     raw_event.get("occurredAt") or self._now_ms(),
            "ingested_at":     self._now_ms(),
        }
        return account_domain, normalized

    def generate_mock_event(self) -> dict[str, Any]:
        """Generate a realistic HubSpot-style CRM activity event."""
        domain = random.choice(_MOCK_COMPANY_DOMAINS)
        first, last = _fake.first_name(), _fake.last_name()
        activity = random.choices(
            population=[
                "contact.creation", "deal.propertyChange",
                "meeting.creation", "meeting.completion",
                "contact.propertyChange", "call.creation",
            ],
            weights=[15, 25, 20, 15, 15, 10],
        )[0]
        deal_stage = random.choice(_MOCK_DEAL_STAGES)
        return {
            "subscriptionType": activity,
            "objectId":         _fake.random_int(min=10000, max=9999999),
            "portalId":         _fake.random_int(min=1000, max=9999),
            "occurredAt":       self._now_ms() - random.randint(0, 3_600_000),
            "propertyName":     "dealstage" if "deal" in activity else "jobtitle",
            "propertyValue":    deal_stage if "deal" in activity else random.choice(_MOCK_TITLES),
            "contact_email":    f"{first.lower()}.{last.lower()}@{domain}",
            "company_domain":   domain,
            "deal_id":          _fake.uuid4() if "deal" in activity else None,
            "deal_stage":       deal_stage if "deal" in activity else None,
            "deal_value_usd":   round(random.uniform(15_000, 500_000), 2)
                                if "deal" in activity else None,
            "crm_source":       "HUBSPOT",
        }
