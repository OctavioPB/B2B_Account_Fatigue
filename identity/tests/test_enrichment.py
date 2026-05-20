"""Tests for identity.enrichment — Clearbit stub, Kickfire stub, and Redis cache."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from identity.enrichment.cache import (
    CachedEnricher,
    CachedIPEnricher,
    _NULL_SENTINEL,
    _deserialize_firm,
    _deserialize_ip,
    _serialize_firm,
    _serialize_ip,
)
from identity.enrichment.clearbit import ClearbitEnricher, _classify_arr_band
from identity.enrichment.kickfire import KickfireIPEnricher
from identity.models import ArrBand, FirmographicData, IPResolutionData


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_redis_mock(cached_value: str | bytes | None = None) -> MagicMock:
    """Return an async mock Redis client."""
    redis = MagicMock()
    redis.get = AsyncMock(return_value=cached_value)
    redis.setex = AsyncMock(return_value=True)
    return redis


# ---------------------------------------------------------------------------
# ClearbitEnricher (stub mode — no API key)
# ---------------------------------------------------------------------------


class TestClearbitEnricherStub:
    @pytest.fixture
    def enricher(self) -> ClearbitEnricher:
        return ClearbitEnricher(api_key=None)

    @pytest.mark.asyncio
    async def test_known_domain_returns_data(self, enricher: ClearbitEnricher) -> None:
        result = await enricher.enrich("salesforce.com")
        assert result is not None
        assert result.domain == "salesforce.com"
        assert result.name == "Salesforce"
        assert result.arr_band == ArrBand.LARGE_ENTERPRISE.value

    @pytest.mark.asyncio
    async def test_source_name_is_clearbit_stub(self, enricher: ClearbitEnricher) -> None:
        result = await enricher.enrich("salesforce.com")
        assert result is not None
        assert result.source == "clearbit_stub"

    @pytest.mark.asyncio
    async def test_unknown_domain_returns_synthetic(self, enricher: ClearbitEnricher) -> None:
        result = await enricher.enrich("unknown-company-xyz.com")
        assert result is not None
        assert result.domain == "unknown-company-xyz.com"
        assert result.name is not None
        assert result.employee_count is not None

    @pytest.mark.asyncio
    async def test_synthetic_is_deterministic(self, enricher: ClearbitEnricher) -> None:
        r1 = await enricher.enrich("mycompany.io")
        r2 = await enricher.enrich("mycompany.io")
        assert r1 is not None and r2 is not None
        assert r1.name == r2.name
        assert r1.industry == r2.industry
        assert r1.employee_count == r2.employee_count

    @pytest.mark.asyncio
    async def test_employee_count_positive(self, enricher: ClearbitEnricher) -> None:
        result = await enricher.enrich("any-company.com")
        assert result is not None
        assert result.employee_count is not None
        assert result.employee_count > 0

    def test_source_name_property(self, enricher: ClearbitEnricher) -> None:
        assert enricher.source_name == "clearbit"


class TestClassifyArrBand:
    @pytest.mark.parametrize(
        "emp, expected",
        [
            (None, ArrBand.SMB.value),
            (5, ArrBand.STARTUP.value),
            (19, ArrBand.STARTUP.value),
            (20, ArrBand.SMB.value),
            (199, ArrBand.SMB.value),
            (200, ArrBand.MID_MARKET.value),
            (999, ArrBand.MID_MARKET.value),
            (1000, ArrBand.ENTERPRISE.value),
            (9999, ArrBand.ENTERPRISE.value),
            (10000, ArrBand.LARGE_ENTERPRISE.value),
            (100000, ArrBand.LARGE_ENTERPRISE.value),
        ],
    )
    def test_classify(self, emp: int | None, expected: str) -> None:
        assert _classify_arr_band(emp) == expected


# ---------------------------------------------------------------------------
# KickfireIPEnricher (stub mode — no API key)
# ---------------------------------------------------------------------------


class TestKickfireIPEnricherStub:
    @pytest.fixture
    def enricher(self) -> KickfireIPEnricher:
        return KickfireIPEnricher(api_key=None)

    @pytest.mark.asyncio
    async def test_known_ip_returns_data(self, enricher: KickfireIPEnricher) -> None:
        result = await enricher.enrich_by_ip("8.8.8.8")
        assert result is not None
        assert result.domain == "google.com"
        assert result.confidence == pytest.approx(0.99)

    @pytest.mark.asyncio
    async def test_high_confidence_ip(self, enricher: KickfireIPEnricher) -> None:
        result = await enricher.enrich_by_ip("192.0.2.1")
        assert result is not None
        assert result.confidence >= 0.70

    @pytest.mark.asyncio
    async def test_low_confidence_ip(self, enricher: KickfireIPEnricher) -> None:
        result = await enricher.enrich_by_ip("203.0.113.1")
        assert result is not None
        assert result.confidence < 0.70

    @pytest.mark.asyncio
    async def test_unknown_ip_returns_synthetic(self, enricher: KickfireIPEnricher) -> None:
        result = await enricher.enrich_by_ip("10.20.30.40")
        assert result is not None
        assert result.domain is not None
        assert 0.0 <= result.confidence <= 1.0

    @pytest.mark.asyncio
    async def test_source_is_kickfire_stub(self, enricher: KickfireIPEnricher) -> None:
        result = await enricher.enrich_by_ip("8.8.8.8")
        assert result is not None
        assert result.source == "kickfire_stub"

    def test_source_name_property(self, enricher: KickfireIPEnricher) -> None:
        assert enricher.source_name == "kickfire"


# ---------------------------------------------------------------------------
# CachedEnricher — Redis wrapping BaseEnricher
# ---------------------------------------------------------------------------


class TestCachedEnricher:
    def _make_firm_data(self, domain: str = "test.com") -> FirmographicData:
        return FirmographicData(
            domain=domain,
            name="Test Corp",
            industry="Technology",
            employee_count=500,
            arr_band=ArrBand.MID_MARKET.value,
            country="US",
            source="clearbit_stub",
        )

    @pytest.mark.asyncio
    async def test_cache_miss_calls_underlying_enricher(self) -> None:
        underlying = MagicMock()
        firm = self._make_firm_data()
        underlying.enrich = AsyncMock(return_value=firm)
        underlying.source_name = "clearbit"
        redis = _make_redis_mock(cached_value=None)

        cached = CachedEnricher(underlying, redis, ttl=3600)
        result = await cached.enrich("test.com")

        underlying.enrich.assert_awaited_once_with("test.com")
        assert result is not None
        assert result.name == "Test Corp"
        redis.setex.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cache_hit_skips_underlying_enricher(self) -> None:
        underlying = MagicMock()
        underlying.enrich = AsyncMock()
        underlying.source_name = "clearbit"
        firm = self._make_firm_data()
        cached_json = _serialize_firm(firm)
        redis = _make_redis_mock(cached_value=cached_json)

        cached = CachedEnricher(underlying, redis, ttl=3600)
        result = await cached.enrich("test.com")

        underlying.enrich.assert_not_awaited()
        assert result is not None
        assert result.name == "Test Corp"

    @pytest.mark.asyncio
    async def test_null_sentinel_returns_none_without_refetch(self) -> None:
        underlying = MagicMock()
        underlying.enrich = AsyncMock()
        underlying.source_name = "clearbit"
        redis = _make_redis_mock(cached_value=_NULL_SENTINEL)

        cached = CachedEnricher(underlying, redis, ttl=3600)
        result = await cached.enrich("noresult.com")

        underlying.enrich.assert_not_awaited()
        assert result is None

    @pytest.mark.asyncio
    async def test_none_result_stored_as_null_sentinel(self) -> None:
        underlying = MagicMock()
        underlying.enrich = AsyncMock(return_value=None)
        underlying.source_name = "clearbit"
        redis = _make_redis_mock(cached_value=None)

        cached = CachedEnricher(underlying, redis, ttl=3600)
        await cached.enrich("unknown.com")

        call_args = redis.setex.call_args
        assert call_args[0][2] == _NULL_SENTINEL

    @pytest.mark.asyncio
    async def test_redis_failure_bypasses_cache(self) -> None:
        underlying = MagicMock()
        firm = self._make_firm_data()
        underlying.enrich = AsyncMock(return_value=firm)
        underlying.source_name = "clearbit"
        redis = MagicMock()
        redis.get = AsyncMock(side_effect=ConnectionError("Redis down"))
        redis.setex = AsyncMock(side_effect=ConnectionError("Redis down"))

        cached = CachedEnricher(underlying, redis, ttl=3600)
        result = await cached.enrich("test.com")

        underlying.enrich.assert_awaited_once()
        assert result is not None  # Still returns data despite Redis being down

    def test_source_name_delegates_to_underlying(self) -> None:
        underlying = MagicMock()
        underlying.source_name = "clearbit"
        redis = _make_redis_mock()
        cached = CachedEnricher(underlying, redis)
        assert cached.source_name == "clearbit"


# ---------------------------------------------------------------------------
# CachedIPEnricher — Redis wrapping BaseIPEnricher
# ---------------------------------------------------------------------------


class TestCachedIPEnricher:
    def _make_ip_data(self, ip: str = "1.2.3.4") -> IPResolutionData:
        return IPResolutionData(
            ip_address=ip,
            domain="acme.com",
            company_name="Acme Corp",
            confidence=0.85,
            source="kickfire_stub",
        )

    @pytest.mark.asyncio
    async def test_cache_miss_calls_underlying(self) -> None:
        underlying = MagicMock()
        ip_data = self._make_ip_data()
        underlying.enrich_by_ip = AsyncMock(return_value=ip_data)
        underlying.source_name = "kickfire"
        redis = _make_redis_mock(cached_value=None)

        cached = CachedIPEnricher(underlying, redis, ttl=3600)
        result = await cached.enrich_by_ip("1.2.3.4")

        underlying.enrich_by_ip.assert_awaited_once_with("1.2.3.4")
        assert result is not None
        assert result.domain == "acme.com"

    @pytest.mark.asyncio
    async def test_cache_hit_skips_underlying(self) -> None:
        underlying = MagicMock()
        underlying.enrich_by_ip = AsyncMock()
        underlying.source_name = "kickfire"
        ip_data = self._make_ip_data()
        cached_json = _serialize_ip(ip_data)
        redis = _make_redis_mock(cached_value=cached_json)

        cached = CachedIPEnricher(underlying, redis, ttl=3600)
        result = await cached.enrich_by_ip("1.2.3.4")

        underlying.enrich_by_ip.assert_not_awaited()
        assert result is not None
        assert result.confidence == pytest.approx(0.85)

    @pytest.mark.asyncio
    async def test_null_sentinel_for_none_result(self) -> None:
        underlying = MagicMock()
        underlying.enrich_by_ip = AsyncMock(return_value=None)
        underlying.source_name = "kickfire"
        redis = _make_redis_mock(cached_value=None)

        cached = CachedIPEnricher(underlying, redis)
        result = await cached.enrich_by_ip("0.0.0.0")
        assert result is None
        call_args = redis.setex.call_args
        assert call_args[0][2] == _NULL_SENTINEL


# ---------------------------------------------------------------------------
# Serialisation round-trip
# ---------------------------------------------------------------------------


class TestSerialisationRoundTrip:
    def test_firmographic_roundtrip(self) -> None:
        firm = FirmographicData(
            domain="roundtrip.com",
            name="Roundtrip Corp",
            industry="Testing",
            employee_count=42,
            arr_band=ArrBand.SMB.value,
            country="GB",
            source="clearbit",
            raw={"extra": "data"},
        )
        serialised = _serialize_firm(firm)
        restored = _deserialize_firm(serialised)
        assert restored.domain == firm.domain
        assert restored.name == firm.name
        assert restored.employee_count == firm.employee_count
        assert restored.raw == firm.raw

    def test_ip_roundtrip(self) -> None:
        ip_data = IPResolutionData(
            ip_address="10.0.0.1",
            domain="roundtrip.com",
            company_name="Roundtrip Corp",
            confidence=0.77,
            source="kickfire",
        )
        serialised = _serialize_ip(ip_data)
        restored = _deserialize_ip(serialised)
        assert restored.ip_address == ip_data.ip_address
        assert restored.domain == ip_data.domain
        assert restored.confidence == pytest.approx(0.77)

    def test_firmographic_roundtrip_with_none_fields(self) -> None:
        firm = FirmographicData(domain="minimal.com")
        serialised = _serialize_firm(firm)
        restored = _deserialize_firm(serialised)
        assert restored.domain == "minimal.com"
        assert restored.name is None
        assert restored.industry is None
