"""Email Engagement Connector.

Receives email engagement webhooks from ESPs (HubSpot Email, Outreach,
Salesloft, Mailchimp) and produces to harmoni.email.engagement.

Negative signals (unsubscribes, bounces, spam reports) are flagged via
is_negative=True to immediately trigger fatigue score recalculation.
"""

from __future__ import annotations

import random
from typing import Any

from faker import Faker

from ingestion.connectors.base import BaseConnector
from ingestion.kafka.topics import EMAIL_ENGAGEMENT, TopicConfig

_fake = Faker()

# Maps source-system event type strings to canonical EmailEngagementType enum
_ENGAGEMENT_TYPE_MAP: dict[str, str] = {
    # HubSpot
    "email.sent":        "SENT",
    "email.delivered":   "DELIVERED",
    "email.opened":      "OPENED",
    "email.clicked":     "CLICKED",
    "email.replied":     "REPLIED",
    "email.unsubscribed":"UNSUBSCRIBED",
    "email.bounced":     "BOUNCED",
    "email.spamreport":  "SPAM_REPORTED",
    # Outreach / Salesloft
    "emailOpen":         "OPENED",
    "emailClick":        "CLICKED",
    "emailReply":        "REPLIED",
    "emailBounce":       "BOUNCED",
    "optOut":            "UNSUBSCRIBED",
    # Generic
    "open":              "OPENED",
    "click":             "CLICKED",
    "reply":             "REPLIED",
    "bounce":            "BOUNCED",
    "unsubscribe":       "UNSUBSCRIBED",
    "spam":              "SPAM_REPORTED",
    "sent":              "SENT",
    "delivered":         "DELIVERED",
    "forwarded":         "FORWARDED",
}

_NEGATIVE_TYPES: frozenset[str] = frozenset(
    {"UNSUBSCRIBED", "BOUNCED", "SPAM_REPORTED"}
)

_MOCK_COMPANY_DOMAINS = [
    "acme-corp.com", "globex.io", "initech.com", "hooli.com",
    "pied-piper.com", "umbrella.co", "wayne-enterprises.com",
]

_MOCK_CAMPAIGNS = [
    ("camp-q3-exec-outreach",   "Q3 Executive Outreach"),
    ("camp-demo-nurture",       "Post-Demo Nurture Sequence"),
    ("camp-pricing-follow-up",  "Pricing Page Follow-Up"),
    ("camp-webinar-invite",     "Webinar Invitation"),
]

_MOCK_SUBJECT_LINES = [
    "Reducing committee fatigue at {company}",
    "Re: Your team's buying process",
    "How {company} could save 40% of deal review time",
    "Quick question about your RevOps stack",
]


class EmailEngagementConnector(BaseConnector):
    """Ingests email engagement events from ESP webhooks."""

    @property
    def topic(self) -> TopicConfig:
        return EMAIL_ENGAGEMENT

    def normalize(
        self, raw_event: dict[str, Any]
    ) -> tuple[str | None, dict[str, Any]]:
        """Normalize an ESP webhook payload to EmailEngagement schema.

        Expected raw_event keys:
            - recipient_email: str
            - event_type: str — mapped via _ENGAGEMENT_TYPE_MAP
            - campaign_id: str (optional)
            - campaign_name: str (optional)
            - message_id: str (optional)
            - click_url: str (optional, for CLICKED events)
            - subject_line: str (optional)
            - sender_email: str (optional)
            - timestamp: int ms (optional, defaults to now)
        """
        email = raw_event.get("recipient_email", "")
        account_domain = self._resolve_domain(email)
        if account_domain is None:
            return None, {}

        raw_type = raw_event.get("event_type", "")
        engagement_type = _ENGAGEMENT_TYPE_MAP.get(raw_type, "SENT")

        normalized: dict[str, Any] = {
            "event_id":        self._new_event_id(),
            "account_domain":  account_domain,
            "contact_email":   email,
            "campaign_id":     raw_event.get("campaign_id"),
            "campaign_name":   raw_event.get("campaign_name"),
            "message_id":      raw_event.get("message_id"),
            "engagement_type": engagement_type,
            "click_url":       raw_event.get("click_url"),
            "subject_line":    raw_event.get("subject_line"),
            "sender_email":    raw_event.get("sender_email"),
            "is_negative":     engagement_type in _NEGATIVE_TYPES,
            "occurred_at":     raw_event.get("timestamp") or self._now_ms(),
            "ingested_at":     self._now_ms(),
        }
        return account_domain, normalized

    def generate_mock_event(self) -> dict[str, Any]:
        """Generate a realistic email engagement event."""
        domain = random.choice(_MOCK_COMPANY_DOMAINS)
        campaign_id, campaign_name = random.choice(_MOCK_CAMPAIGNS)
        event_type = random.choices(
            population=["open", "click", "reply", "sent", "unsubscribe"],
            weights=[40, 25, 10, 20, 5],
        )[0]
        return {
            "recipient_email": _fake.user_name() + "@" + domain,
            "event_type":      event_type,
            "campaign_id":     campaign_id,
            "campaign_name":   campaign_name,
            "message_id":      _fake.uuid4(),
            "subject_line":    random.choice(_MOCK_SUBJECT_LINES).format(
                company=domain.split(".")[0].title()
            ),
            "sender_email":    "outreach@harmoni.io",
            "click_url":       (
                "https://harmoni.io/pricing"
                if event_type == "click"
                else None
            ),
            "timestamp":       self._now_ms() - random.randint(0, 86_400_000),
        }
