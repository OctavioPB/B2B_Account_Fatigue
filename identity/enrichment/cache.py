"""Redis-backed caching wrappers for enrichment providers.

CachedEnricher   — wraps any BaseEnricher with a Redis TTL cache
CachedIPEnricher — wraps any BaseIPEnricher with a Redis TTL cache

Cache key format:
    enricher:firm:{source_name}:{domain}
    enricher:ip:{source_name}:{ip_address}

Values are JSON-serialised FirmographicData / IPResolutionData dicts.
A ``None`` result (no record found) is cached as the sentinel ``"null"``
to prevent repeated expensive misses within the TTL window.

The Redis client must be an async redis.asyncio.Redis instance.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import redis.asyncio as aioredis

from identity.enrichment.base import BaseEnricher, BaseIPEnricher
from identity.models import FirmographicData, IPResolutionData

logger = logging.getLogger(__name__)

_NULL_SENTINEL = "null"

# Default TTL: 24 hours (firmographic data is relatively stable)
_DEFAULT_FIRM_TTL = 86_400
# IP data can change more frequently; shorter TTL
_DEFAULT_IP_TTL = 3_600


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)


class CachedEnricher(BaseEnricher):
    """Redis-memoised wrapper around any BaseEnricher implementation.

    Args:
        enricher: The underlying enricher to delegate cache misses to.
        redis:    Async Redis client (``redis.asyncio.Redis``).
        ttl:      Cache TTL in seconds (default 86400).
    """

    def __init__(
        self,
        enricher: BaseEnricher,
        redis: "aioredis.Redis",  # type: ignore[type-arg]
        ttl: int = _DEFAULT_FIRM_TTL,
    ) -> None:
        self._enricher = enricher
        self._redis = redis
        self._ttl = ttl

    @property
    def source_name(self) -> str:
        return self._enricher.source_name

    def _cache_key(self, domain: str) -> str:
        return f"enricher:firm:{self.source_name}:{domain}"

    async def enrich(self, domain: str) -> FirmographicData | None:
        key = self._cache_key(domain)
        try:
            cached = await self._redis.get(key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis GET failed for %s: %s — bypassing cache", key, exc)
            cached = None

        if cached is not None:
            if cached == _NULL_SENTINEL:
                return None
            try:
                return _deserialize_firm(cached)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Cache deserialise error for %s: %s — refetching", key, exc)

        result = await self._enricher.enrich(domain)
        payload = _NULL_SENTINEL if result is None else _serialize_firm(result)
        try:
            await self._redis.setex(key, self._ttl, payload)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis SETEX failed for %s: %s", key, exc)

        return result


class CachedIPEnricher(BaseIPEnricher):
    """Redis-memoised wrapper around any BaseIPEnricher implementation.

    Args:
        enricher: The underlying IP enricher to delegate cache misses to.
        redis:    Async Redis client.
        ttl:      Cache TTL in seconds (default 3600).
    """

    def __init__(
        self,
        enricher: BaseIPEnricher,
        redis: "aioredis.Redis",  # type: ignore[type-arg]
        ttl: int = _DEFAULT_IP_TTL,
    ) -> None:
        self._enricher = enricher
        self._redis = redis
        self._ttl = ttl

    @property
    def source_name(self) -> str:
        return self._enricher.source_name

    def _cache_key(self, ip_address: str) -> str:
        return f"enricher:ip:{self.source_name}:{ip_address}"

    async def enrich_by_ip(self, ip_address: str) -> IPResolutionData | None:
        key = self._cache_key(ip_address)
        try:
            cached = await self._redis.get(key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis GET failed for %s: %s — bypassing cache", key, exc)
            cached = None

        if cached is not None:
            if cached == _NULL_SENTINEL:
                return None
            try:
                return _deserialize_ip(cached)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Cache deserialise error for %s: %s — refetching", key, exc)

        result = await self._enricher.enrich_by_ip(ip_address)
        payload = _NULL_SENTINEL if result is None else _serialize_ip(result)
        try:
            await self._redis.setex(key, self._ttl, payload)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis SETEX failed for %s: %s", key, exc)

        return result


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _serialize_firm(data: FirmographicData) -> str:
    return json.dumps({
        "domain": data.domain,
        "name": data.name,
        "industry": data.industry,
        "employee_count": data.employee_count,
        "arr_band": data.arr_band,
        "country": data.country,
        "source": data.source,
        "enriched_at": data.enriched_at.isoformat() if data.enriched_at else None,
        "raw": data.raw,
    })


def _deserialize_firm(raw: str | bytes) -> FirmographicData:
    d = json.loads(raw)
    return FirmographicData(
        domain=d["domain"],
        name=d.get("name"),
        industry=d.get("industry"),
        employee_count=d.get("employee_count"),
        arr_band=d.get("arr_band"),
        country=d.get("country"),
        source=d.get("source", "unknown"),
        enriched_at=_parse_datetime(d.get("enriched_at")) or datetime.now(timezone.utc),
        raw=d.get("raw", {}),
    )


def _serialize_ip(data: IPResolutionData) -> str:
    return json.dumps({
        "ip_address": data.ip_address,
        "domain": data.domain,
        "company_name": data.company_name,
        "confidence": data.confidence,
        "source": data.source,
        "resolved_at": data.resolved_at.isoformat() if data.resolved_at else None,
    })


def _deserialize_ip(raw: str | bytes) -> IPResolutionData:
    d = json.loads(raw)
    return IPResolutionData(
        ip_address=d["ip_address"],
        domain=d.get("domain"),
        company_name=d.get("company_name"),
        confidence=float(d.get("confidence", 0.0)),
        source=d.get("source", "unknown"),
        resolved_at=_parse_datetime(d.get("resolved_at")) or datetime.now(timezone.utc),
    )
