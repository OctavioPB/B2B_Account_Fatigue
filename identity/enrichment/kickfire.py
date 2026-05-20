"""KickFire IP-to-company enricher.

Production path: HTTP GET to ``https://api.kickfire.com/v3/company?ip=<ip>&key=<key>``

When ``KICKFIRE_API_KEY`` is absent the class operates in stub mode:
a fixed mapping of well-known IP ranges to companies, plus a deterministic
fallback for arbitrary IPs that returns a low-confidence result.

Environment variables:
    KICKFIRE_API_KEY  — if absent, stub mode is used
    KICKFIRE_TIMEOUT  — HTTP timeout in seconds (default 5)

Confidence scoring:
    The Kickfire API returns a ``confidence`` field (1–100 integer). We
    normalise to 0.0–1.0. The ``AsyncAccountResolver`` treats results
    ≥ 0.70 as MEDIUM confidence and < 0.70 as LOW.
"""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx

from identity.enrichment.base import BaseIPEnricher
from identity.models import IPResolutionData

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stub IP → company mapping (covers common test fixtures)
# ---------------------------------------------------------------------------

_KNOWN_IPS: dict[str, dict[str, Any]] = {
    "8.8.8.8":       {"domain": "google.com",     "company_name": "Google LLC",      "confidence": 0.99},
    "13.32.0.1":     {"domain": "amazon.com",      "company_name": "Amazon.com Inc.", "confidence": 0.95},
    "20.236.44.162": {"domain": "microsoft.com",   "company_name": "Microsoft Corp.", "confidence": 0.93},
    "104.16.0.1":    {"domain": "cloudflare.com",  "company_name": "Cloudflare Inc.", "confidence": 0.92},
    "192.0.2.1":     {"domain": "acme.com",         "company_name": "Acme Corporation","confidence": 0.85},
    "198.51.100.1":  {"domain": "testcorp.com",     "company_name": "TestCorp Ltd.",   "confidence": 0.75},
    "203.0.113.1":   {"domain": "example-b2b.com", "company_name": "Example B2B Co.", "confidence": 0.60},
}

_SYNTHETIC_DOMAINS = [
    "tech-startup.io", "saas-vendor.com", "enterprise-co.com",
    "digital-agency.net", "consulting-firm.biz",
]


def _synthetic_ip_result(ip: str) -> dict[str, Any]:
    seed = int(hashlib.md5(ip.encode()).hexdigest(), 16)  # noqa: S324
    domain = _SYNTHETIC_DOMAINS[seed % len(_SYNTHETIC_DOMAINS)]
    # Confidence 0.45–0.68 — keeps it in LOW range for unknown IPs
    raw_conf = 45 + (seed % 24)
    return {
        "domain": domain,
        "company_name": domain.split(".")[0].title() + " Corp",
        "confidence": raw_conf / 100,
    }


class KickfireIPEnricher(BaseIPEnricher):
    """IP-to-company enricher backed by KickFire API.

    Operates in stub mode when ``KICKFIRE_API_KEY`` is not set.
    """

    _BASE_URL = "https://api.kickfire.com/v3/company"

    def __init__(
        self,
        api_key: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self._api_key: str | None = api_key or os.getenv("KICKFIRE_API_KEY")
        self._timeout = timeout or float(os.getenv("KICKFIRE_TIMEOUT", "5"))

    @property
    def source_name(self) -> str:
        return "kickfire"

    async def enrich_by_ip(self, ip_address: str) -> IPResolutionData | None:
        if self._api_key:
            return await self._call_api(ip_address)
        return self._stub_enrich(ip_address)

    async def _call_api(self, ip_address: str) -> IPResolutionData | None:
        params = {"ip": ip_address, "key": self._api_key}
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                resp = await client.get(self._BASE_URL, params=params)
            except httpx.RequestError as exc:
                logger.warning("KickFire HTTP error for IP %s: %s", ip_address, exc)
                return None

        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            logger.warning("KickFire unexpected status %d for IP %s", resp.status_code, ip_address)
            return None

        raw: dict[str, Any] = resp.json()
        return self._parse_response(ip_address, raw)

    def _parse_response(self, ip_address: str, raw: dict[str, Any]) -> IPResolutionData | None:
        data = raw.get("data", [{}])
        if not data:
            return None
        record = data[0] if isinstance(data, list) else data
        domain: str | None = record.get("website") or record.get("domain")
        if not domain:
            return None
        raw_confidence = float(record.get("confidence", 0))
        confidence = raw_confidence / 100 if raw_confidence > 1 else raw_confidence
        return IPResolutionData(
            ip_address=ip_address,
            domain=domain.lower().lstrip("www."),
            company_name=record.get("companyName"),
            confidence=min(max(confidence, 0.0), 1.0),
            source=self.source_name,
            resolved_at=datetime.now(timezone.utc),
        )

    def _stub_enrich(self, ip_address: str) -> IPResolutionData | None:
        data = _KNOWN_IPS.get(ip_address) or _synthetic_ip_result(ip_address)
        return IPResolutionData(
            ip_address=ip_address,
            domain=data["domain"],
            company_name=data["company_name"],
            confidence=data["confidence"],
            source=f"{self.source_name}_stub",
            resolved_at=datetime.now(timezone.utc),
        )
