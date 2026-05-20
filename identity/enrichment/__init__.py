"""Account identity enrichment providers.

Public surface:
    BaseEnricher        — abstract firmographic enricher protocol
    BaseIPEnricher      — abstract IP-to-company enricher protocol
    ClearbitEnricher    — Clearbit Company API (firmographic)
    KickfireIPEnricher  — KickFire IP-to-company API
    CachedEnricher      — Redis-backed caching wrapper (any BaseEnricher)
    CachedIPEnricher    — Redis-backed caching wrapper (any BaseIPEnricher)
"""

from identity.enrichment.base import BaseEnricher, BaseIPEnricher
from identity.enrichment.cache import CachedEnricher, CachedIPEnricher
from identity.enrichment.clearbit import ClearbitEnricher
from identity.enrichment.kickfire import KickfireIPEnricher

__all__ = [
    "BaseEnricher",
    "BaseIPEnricher",
    "ClearbitEnricher",
    "KickfireIPEnricher",
    "CachedEnricher",
    "CachedIPEnricher",
]
