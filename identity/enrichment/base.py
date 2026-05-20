"""Abstract base classes for harmoni enrichment providers.

Two enricher protocols:

BaseEnricher
    Firmographic enrichment: given a domain, returns FirmographicData
    (company name, industry, employee count, ARR band, country).

BaseIPEnricher
    IP-to-company resolution: given an IPv4/IPv6 address, returns
    IPResolutionData with a domain and a confidence score (0.0–1.0).

Both are injected into AsyncAccountResolver and the ResolutionPipeline.
Implementations (Clearbit, KickFire) live in sibling modules. The
CachedEnricher/CachedIPEnricher wrappers add Redis memoisation on top.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from identity.models import FirmographicData, IPResolutionData


class BaseEnricher(ABC):
    """Firmographic enrichment provider contract."""

    @abstractmethod
    async def enrich(self, domain: str) -> "FirmographicData | None":
        """Look up firmographic data for a domain.

        Args:
            domain: Normalised company domain (e.g. ``acme.com``).

        Returns:
            Populated :class:`~identity.models.FirmographicData`, or
            ``None`` if the provider has no record for this domain.
        """

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Short identifier written to ``FirmographicData.source`` (e.g. ``"clearbit"``)."""


class BaseIPEnricher(ABC):
    """IP-to-company enrichment provider contract."""

    @abstractmethod
    async def enrich_by_ip(self, ip_address: str) -> "IPResolutionData | None":
        """Resolve an IP address to a company domain.

        Args:
            ip_address: IPv4 or IPv6 address string.

        Returns:
            :class:`~identity.models.IPResolutionData` with domain and
            confidence, or ``None`` if the IP cannot be attributed.
        """

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Short identifier written to ``IPResolutionData.source``."""
