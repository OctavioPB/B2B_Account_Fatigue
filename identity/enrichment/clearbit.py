"""Clearbit Company API enricher.

Production path: HTTP GET to ``https://company.clearbit.com/v2/companies/find?domain=<domain>``
with ``Authorization: Bearer <CLEARBIT_API_KEY>``.

In the absence of a live key the class falls back to a deterministic mock
that returns plausible data for a set of well-known B2B SaaS domains and
generates synthetic-but-stable records for everything else (keyed on domain).
This lets integration tests run without an API key.

Environment variables:
    CLEARBIT_API_KEY  — if absent, stub mode is used
    CLEARBIT_TIMEOUT  — HTTP request timeout in seconds (default 5)
"""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx

from identity.enrichment.base import BaseEnricher
from identity.models import ArrBand, FirmographicData

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Curated mock data for well-known domains (deterministic; used in tests)
# ---------------------------------------------------------------------------

_KNOWN_DOMAINS: dict[str, dict[str, Any]] = {
    "salesforce.com": {
        "name": "Salesforce",
        "industry": "CRM Software",
        "employee_count": 73000,
        "arr_band": ArrBand.LARGE_ENTERPRISE.value,
        "country": "US",
    },
    "hubspot.com": {
        "name": "HubSpot",
        "industry": "Marketing Software",
        "employee_count": 7400,
        "arr_band": ArrBand.ENTERPRISE.value,
        "country": "US",
    },
    "stripe.com": {
        "name": "Stripe",
        "industry": "FinTech",
        "employee_count": 8000,
        "arr_band": ArrBand.ENTERPRISE.value,
        "country": "US",
    },
    "notion.so": {
        "name": "Notion",
        "industry": "Productivity Software",
        "employee_count": 400,
        "arr_band": ArrBand.MID_MARKET.value,
        "country": "US",
    },
    "acme.com": {
        "name": "Acme Corporation",
        "industry": "Technology",
        "employee_count": 250,
        "arr_band": ArrBand.MID_MARKET.value,
        "country": "US",
    },
}

_INDUSTRIES = [
    "Technology", "FinTech", "Healthcare IT", "Manufacturing", "Retail",
    "Professional Services", "Education", "Media & Entertainment",
]

_ARR_BANDS = [
    ArrBand.STARTUP.value,
    ArrBand.SMB.value,
    ArrBand.MID_MARKET.value,
    ArrBand.ENTERPRISE.value,
]

_COUNTRIES = ["US", "GB", "DE", "CA", "AU", "FR", "NL", "SE", "SG", "IN"]


def _synthetic_firmographic(domain: str) -> dict[str, Any]:
    """Deterministically derive plausible firmographic data from the domain string."""
    seed = int(hashlib.md5(domain.encode()).hexdigest(), 16)  # noqa: S324
    return {
        "name": domain.split(".")[0].title() + " Inc.",
        "industry": _INDUSTRIES[seed % len(_INDUSTRIES)],
        "employee_count": (seed % 9 + 1) * 50,
        "arr_band": _ARR_BANDS[seed % len(_ARR_BANDS)],
        "country": _COUNTRIES[seed % len(_COUNTRIES)],
    }


class ClearbitEnricher(BaseEnricher):
    """Firmographic enricher backed by Clearbit Company API.

    Falls back to deterministic stub data when ``CLEARBIT_API_KEY`` is not set.
    """

    _BASE_URL = "https://company.clearbit.com/v2/companies/find"

    def __init__(
        self,
        api_key: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self._api_key: str | None = api_key or os.getenv("CLEARBIT_API_KEY")
        self._timeout = timeout or float(os.getenv("CLEARBIT_TIMEOUT", "5"))

    @property
    def source_name(self) -> str:
        return "clearbit"

    async def enrich(self, domain: str) -> FirmographicData | None:
        if self._api_key:
            return await self._call_api(domain)
        return self._stub_enrich(domain)

    async def _call_api(self, domain: str) -> FirmographicData | None:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        params = {"domain": domain}
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                resp = await client.get(self._BASE_URL, headers=headers, params=params)
            except httpx.RequestError as exc:
                logger.warning("Clearbit HTTP error for %s: %s", domain, exc)
                return None

        if resp.status_code == 404:
            return None
        if resp.status_code == 402:
            logger.warning("Clearbit quota exceeded (402); falling back to stub for %s", domain)
            return self._stub_enrich(domain)
        if resp.status_code != 200:
            logger.warning("Clearbit unexpected status %d for %s", resp.status_code, domain)
            return None

        raw: dict[str, Any] = resp.json()
        return self._parse_response(domain, raw)

    def _parse_response(self, domain: str, raw: dict[str, Any]) -> FirmographicData:
        metrics = raw.get("metrics", {})
        employee_count: int | None = (
            metrics.get("employees") or metrics.get("employeesRange")
        )
        if isinstance(employee_count, str):
            # employeesRange is a string like "1-10"
            try:
                employee_count = int(employee_count.split("-")[0])
            except (ValueError, IndexError):
                employee_count = None

        arr_band = _classify_arr_band(employee_count)

        return FirmographicData(
            domain=domain,
            name=raw.get("name"),
            industry=raw.get("category", {}).get("industry"),
            employee_count=employee_count,
            arr_band=arr_band,
            country=raw.get("geo", {}).get("country"),
            source=self.source_name,
            enriched_at=datetime.now(timezone.utc),
            raw=raw,
        )

    def _stub_enrich(self, domain: str) -> FirmographicData | None:
        data = _KNOWN_DOMAINS.get(domain) or _synthetic_firmographic(domain)
        return FirmographicData(
            domain=domain,
            name=data["name"],
            industry=data["industry"],
            employee_count=data["employee_count"],
            arr_band=data["arr_band"],
            country=data["country"],
            source=f"{self.source_name}_stub",
            enriched_at=datetime.now(timezone.utc),
            raw=data,
        )


def _classify_arr_band(employee_count: int | None) -> str:
    """Approximate ARR band from headcount (heuristic only)."""
    if employee_count is None:
        return ArrBand.SMB.value
    if employee_count < 20:
        return ArrBand.STARTUP.value
    if employee_count < 200:
        return ArrBand.SMB.value
    if employee_count < 1000:
        return ArrBand.MID_MARKET.value
    if employee_count < 10000:
        return ArrBand.ENTERPRISE.value
    return ArrBand.LARGE_ENTERPRISE.value
