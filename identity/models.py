"""harmoni identity data models.

Immutable dataclasses that represent domain entities. These are the canonical
Python representations used across the resolution pipeline. Database mapping
is handled by identity.repository; SCD Type 2 wrapping is added in Sprint 4.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class SeniorityLevel(str, Enum):
    """Buying-committee stakeholder seniority — drives role_weight in IntentNetworkModel."""

    C_SUITE = "C_SUITE"
    VP = "VP"
    DIRECTOR = "DIRECTOR"
    MANAGER = "MANAGER"
    IC = "IC"  # Individual Contributor


class AliasType(str, Enum):
    """Why an alias domain maps to a canonical domain."""

    ACQUISITION = "ACQUISITION"
    REBRAND = "REBRAND"
    SUBSIDIARY = "SUBSIDIARY"
    MANUAL = "MANUAL"


class ArrBand(str, Enum):
    """Annual Recurring Revenue band for firmographic segmentation."""

    STARTUP = "STARTUP"          # < $1M
    SMB = "SMB"                  # $1M – $10M
    MID_MARKET = "MID_MARKET"    # $10M – $50M
    ENTERPRISE = "ENTERPRISE"    # $50M – $500M
    LARGE_ENTERPRISE = "LARGE_ENTERPRISE"  # > $500M


# Role weight by seniority — feeds IntentNetworkModel (Sprint 5)
ROLE_WEIGHTS: dict[SeniorityLevel, float] = {
    SeniorityLevel.C_SUITE:  1.00,
    SeniorityLevel.VP:       0.80,
    SeniorityLevel.DIRECTOR: 0.60,
    SeniorityLevel.MANAGER:  0.40,
    SeniorityLevel.IC:       0.20,
}

# Title keyword patterns → seniority (longest/highest-priority first)
_SENIORITY_RULES: list[tuple[re.Pattern[str], SeniorityLevel]] = [
    (re.compile(r"\b(chief|ceo|cfo|cto|coo|ciso|cmo|president|founder|owner)\b"), SeniorityLevel.C_SUITE),
    (re.compile(r"\b(evp|svp|vp|vice president|vice-president)\b"),               SeniorityLevel.VP),
    (re.compile(r"\b(director|head of|principal)\b"),                              SeniorityLevel.DIRECTOR),
    (re.compile(r"\b(manager|lead|senior|sr\.?)\b"),                               SeniorityLevel.MANAGER),
]


def infer_seniority(title: str | None) -> SeniorityLevel:
    """Classify a job title string into a SeniorityLevel.

    Args:
        title: Raw job title (e.g. "VP of Revenue Operations").

    Returns:
        Best-matching SeniorityLevel; defaults to IC if no rule matches.
    """
    if not title:
        return SeniorityLevel.IC
    lower = title.lower()
    for pattern, level in _SENIORITY_RULES:
        if pattern.search(lower):
            return level
    return SeniorityLevel.IC


# ---------------------------------------------------------------------------
# Domain entities
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Account:
    """A target B2B company, keyed by normalized email domain."""

    id: str
    domain: str
    name: str | None = None
    industry: str | None = None
    employee_count: int | None = None
    arr_band: str | None = None
    country: str | None = None
    firmographic_source: str | None = None
    firmographic_enriched_at: datetime | None = None
    raw_firmographic: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)


@dataclass
class CommitteeMember:
    """An individual buying-committee stakeholder linked to an Account."""

    id: str
    account_id: str
    email: str
    first_name: str | None = None
    last_name: str | None = None
    title: str | None = None
    department: str | None = None
    seniority_level: SeniorityLevel = SeniorityLevel.IC
    role_weight: float = ROLE_WEIGHTS[SeniorityLevel.IC]
    crm_contact_id: str | None = None
    crm_source: str | None = None
    is_active: bool = True
    last_signal_at: datetime | None = None
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    def display_name(self) -> str:
        if self.first_name or self.last_name:
            return f"{self.first_name or ''} {self.last_name or ''}".strip()
        return self.email.split("@")[0]


@dataclass
class DomainAlias:
    """An alias domain that maps to a canonical account domain.

    e.g. acquired-startup.io → corp.com (AliasType.ACQUISITION)
    """

    id: str
    alias_domain: str
    canonical_domain: str
    alias_type: AliasType = AliasType.MANUAL
    note: str | None = None
    effective_from: datetime = field(default_factory=_utcnow)
    effective_to: datetime | None = None  # None = currently active
    created_at: datetime = field(default_factory=_utcnow)

    @property
    def is_active(self) -> bool:
        now = _utcnow()
        return self.effective_from <= now and (
            self.effective_to is None or self.effective_to > now
        )


@dataclass
class CRMAccountXRef:
    """Cross-reference: CRM company ID → canonical account domain."""

    id: str
    canonical_domain: str
    crm_source: str   # 'HUBSPOT' | 'SALESFORCE' | 'PIPEDRIVE'
    crm_company_id: str
    crm_company_name: str | None = None
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)


@dataclass
class FirmographicData:
    """Enriched firmographic attributes for an account domain."""

    domain: str
    name: str | None = None
    industry: str | None = None
    employee_count: int | None = None
    arr_band: str | None = None
    country: str | None = None
    source: str = "unknown"  # 'clearbit' | 'kickfire' | 'manual'
    enriched_at: datetime = field(default_factory=_utcnow)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class IPResolutionData:
    """Result of resolving an IP address to a company."""

    ip_address: str
    domain: str | None
    company_name: str | None = None
    confidence: float = 0.0  # 0.0 – 1.0
    source: str = "unknown"  # 'kickfire' | 'clearbit_reveal' | 'manual'
    resolved_at: datetime = field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# Resolution I/O
# ---------------------------------------------------------------------------


@dataclass
class ResolutionInput:
    """All available signals for resolving an event to an Account."""

    email: str | None = None
    ip_address: str | None = None
    crm_contact_id: str | None = None
    crm_company_id: str | None = None
    crm_source: str | None = None
    explicit_domain: str | None = None  # pre-resolved domain (trust unconditionally)
    source_event_id: str = ""
    source_topic: str = ""
    raw_context: dict[str, Any] = field(default_factory=dict)


@dataclass
class QuarantineEntry:
    """A quarantined event awaiting manual resolution."""

    id: str
    event_id: str
    source_topic: str
    raw_event: dict[str, Any]
    resolution_attempt: dict[str, Any]
    confidence: str  # ResolutionConfidence value
    status: str = "PENDING"
    reviewed_by: str | None = None
    resolved_domain: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime = field(default_factory=_utcnow)
