"""Web Analytics Connector.

Ingests server-side pageview events (tracking pixel callbacks, server log lines,
GA4 Measurement Protocol hits) and produces to harmoni.web.pageview.

PageCategory classification is heuristic — override for custom URL structures.
"""

from __future__ import annotations

import random
from typing import Any

from faker import Faker

from ingestion.connectors.base import BaseConnector
from ingestion.kafka.topics import WEB_PAGEVIEW, TopicConfig

_fake = Faker()

# URL patterns → PageCategory mapping (longest-match first)
_URL_CATEGORY_RULES: list[tuple[str, str]] = [
    ("/pricing",      "PRICING"),
    ("/price",        "PRICING"),
    ("/plans",        "PRICING"),
    ("/product",      "PRODUCT"),
    ("/features",     "PRODUCT"),
    ("/platform",     "PRODUCT"),
    ("/demo",         "DEMO"),
    ("/request-demo", "DEMO"),
    ("/blog",         "BLOG"),
    ("/case-study",   "CASE_STUDY"),
    ("/customers",    "CASE_STUDY"),
    ("/docs",         "DOCS"),
    ("/documentation","DOCS"),
    ("/api",          "DOCS"),
]

_MOCK_COMPANY_DOMAINS = [
    "acme-corp.com", "globex.io", "initech.com", "hooli.com",
    "pied-piper.com", "umbrella.co", "wayne-enterprises.com",
    "stark-industries.com", "cyberdyne.io", "soylent.com",
]

_MOCK_PAGES: list[tuple[str, str]] = [
    ("/pricing",                     "Pricing & Plans · harmoni"),
    ("/product/fatigue-score",       "Account Fatigue Score · harmoni"),
    ("/demo",                        "Request a Demo · harmoni"),
    ("/case-study/enterprise-growth","Case Study: 3× Pipeline Velocity"),
    ("/docs/api",                    "API Reference · harmoni"),
    ("/blog/b2b-buying-committees",  "The Hidden Cost of Buying Committee Fatigue"),
]


def _classify_page(url: str) -> str:
    url_lower = url.lower()
    for prefix, category in _URL_CATEGORY_RULES:
        if prefix in url_lower:
            return category
    return "OTHER"


class WebAnalyticsConnector(BaseConnector):
    """Ingests web analytics pageview events."""

    @property
    def topic(self) -> TopicConfig:
        return WEB_PAGEVIEW

    def normalize(
        self, raw_event: dict[str, Any]
    ) -> tuple[str | None, dict[str, Any]]:
        """Normalize a raw pixel/GA4 event to WebPageview schema.

        Expected raw_event keys (GA4 Measurement Protocol style):
            - contact_email: str — resolves account_domain
            - page_location: str — full URL
            - page_title: str (optional)
            - document_referrer: str (optional)
            - session_id: str (optional)
            - ip_address: str (optional)
            - user_agent: str (optional)
            - time_on_page: int seconds (optional)
            - utm_source / utm_medium / utm_campaign (optional)
        """
        email = raw_event.get("contact_email", "")
        account_domain = self._resolve_domain(email) if email else None

        # Fall back to ip_address-based resolution (Sprint 3 enrichment)
        if account_domain is None and raw_event.get("ip_address"):
            account_domain = raw_event.get("resolved_domain")  # set by resolver layer

        if account_domain is None:
            return None, {}

        page_url = raw_event.get("page_location") or raw_event.get("url", "")

        normalized: dict[str, Any] = {
            "event_id":              self._new_event_id(),
            "account_domain":        account_domain,
            "session_id":            raw_event.get("session_id") or self._new_event_id(),
            "page_url":              page_url,
            "page_category":         _classify_page(page_url),
            "page_title":            raw_event.get("page_title"),
            "referrer_url":          raw_event.get("document_referrer"),
            "utm_source":            raw_event.get("utm_source"),
            "utm_medium":            raw_event.get("utm_medium"),
            "utm_campaign":          raw_event.get("utm_campaign"),
            "ip_address":            raw_event.get("ip_address"),
            "user_agent":            raw_event.get("user_agent"),
            "time_on_page_seconds":  raw_event.get("time_on_page"),
            "occurred_at":           raw_event.get("occurred_at") or self._now_ms(),
            "ingested_at":           self._now_ms(),
        }
        return account_domain, normalized

    def generate_mock_event(self) -> dict[str, Any]:
        """Generate a realistic web pageview event for a random B2B company."""
        domain = random.choice(_MOCK_COMPANY_DOMAINS)
        page_url, page_title = random.choice(_MOCK_PAGES)
        return {
            "contact_email":   _fake.user_name() + "@" + domain,
            "page_location":   "https://harmoni.io" + page_url,
            "page_title":      page_title,
            "document_referrer": random.choice([
                "https://google.com/search",
                "https://linkedin.com",
                "https://g2.com",
                None,
            ]),
            "session_id":      _fake.uuid4(),
            "ip_address":      _fake.ipv4(),
            "user_agent":      _fake.user_agent(),
            "time_on_page":    random.randint(5, 420),
            "utm_source":      random.choice(["google", "linkedin", "email", None]),
            "utm_medium":      random.choice(["cpc", "organic", "newsletter", None]),
            "utm_campaign":    random.choice(["q3-abm", "brand", "retarget", None]),
            "occurred_at":     self._now_ms() - random.randint(0, 3600_000),
        }
