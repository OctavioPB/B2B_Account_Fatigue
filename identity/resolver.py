"""Account identity resolution engine.

Two resolver classes:

AccountResolver (sync, stateless)
    Sprint 1 foundation. Pure domain logic — no DB or network calls.
    Used in connectors for fast pre-flight quarantine decisions.

AsyncAccountResolver (async, database + enrichment backed)
    Sprint 3 full implementation. Runs all four strategies in waterfall order
    per ADR 0005, then returns a ResolutionResult with confidence tier.
    Injected with repositories and enrichers for testability.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from identity.enrichment.base import BaseEnricher, BaseIPEnricher
    from identity.repository import AccountRepository

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Free-email domain blocklist
# ---------------------------------------------------------------------------

_FREE_EMAIL_DOMAINS: frozenset[str] = frozenset(
    {
        "gmail.com", "googlemail.com",
        "yahoo.com", "yahoo.co.uk", "yahoo.fr", "yahoo.de",
        "hotmail.com", "hotmail.co.uk", "hotmail.fr",
        "outlook.com", "live.com", "msn.com",
        "icloud.com", "me.com", "mac.com",
        "protonmail.com", "proton.me",
        "aol.com", "ymail.com",
        "zoho.com",
        "gmx.com", "gmx.net",
        "mail.com", "inbox.com",
        "fastmail.com", "fastmail.fm",
        "tutanota.com", "tutamail.com",
        "hey.com",
    }
)

_DOMAIN_RE = re.compile(r"^[a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?(\.[a-z]{2,})+$")


# ---------------------------------------------------------------------------
# Core types
# ---------------------------------------------------------------------------


class ResolutionConfidence(str, Enum):
    """Confidence tier per ADR 0005."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNRESOLVABLE = "UNRESOLVABLE"


@dataclass(frozen=True)
class ResolutionResult:
    """Outcome of resolving a signal to an Account domain."""

    domain: str | None
    account_id: str | None
    confidence: ResolutionConfidence
    strategy: str
    reason: str | None = None

    def is_actionable(self) -> bool:
        """True when this result is good enough to proceed to scoring."""
        return self.confidence in (ResolutionConfidence.HIGH, ResolutionConfidence.MEDIUM)

    def needs_quarantine(self) -> bool:
        return self.confidence in (ResolutionConfidence.LOW, ResolutionConfidence.UNRESOLVABLE)


# ---------------------------------------------------------------------------
# Domain utility functions (public API — also imported by connectors)
# ---------------------------------------------------------------------------


def normalize_domain(email_or_domain: str) -> str:
    """Extract and lowercase the domain from an email address or bare domain.

    Canonical account key function per ADR 0001.
    Strips leading 'www.' and lowercases; all other subdomains are preserved.

    >>> normalize_domain("Alice@ACME.COM")
    'acme.com'
    >>> normalize_domain("www.acme.com")
    'acme.com'
    """
    raw = email_or_domain.strip().lower()
    domain = raw.split("@")[-1]
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def is_free_email_domain(domain: str) -> bool:
    """Return True for consumer free-email providers that cannot identify a B2B account."""
    return normalize_domain(domain) in _FREE_EMAIL_DOMAINS


def is_valid_domain(domain: str) -> bool:
    """Return True if the string is a syntactically valid domain name."""
    normalized = normalize_domain(domain)
    return bool(_DOMAIN_RE.match(normalized))


def extract_domain_from_email(email: str) -> str | None:
    """Return normalized business domain, or None if free / invalid."""
    domain = normalize_domain(email)
    if not is_valid_domain(domain) or is_free_email_domain(domain):
        return None
    return domain


# ---------------------------------------------------------------------------
# Sync resolver (Sprint 1 — pure in-memory, used by connectors)
# ---------------------------------------------------------------------------


class AccountResolver:
    """Stateless, synchronous resolver using only domain-level logic.

    Suitable for connector pre-flight checks and unit tests that cannot
    tolerate async / DB calls. For full multi-strategy resolution, use
    AsyncAccountResolver.
    """

    def resolve_from_email(self, email: str) -> ResolutionResult:
        domain = normalize_domain(email)
        if not is_valid_domain(domain):
            return ResolutionResult(
                domain=None, account_id=None,
                confidence=ResolutionConfidence.UNRESOLVABLE,
                strategy="email_domain",
                reason=f"Invalid domain: {domain!r}",
            )
        if is_free_email_domain(domain):
            return ResolutionResult(
                domain=None, account_id=None,
                confidence=ResolutionConfidence.UNRESOLVABLE,
                strategy="email_domain",
                reason=f"Free email domain: {domain!r}",
            )
        return ResolutionResult(
            domain=domain, account_id=None,
            confidence=ResolutionConfidence.HIGH,
            strategy="email_domain",
        )

    def resolve_from_domain(self, domain: str) -> ResolutionResult:
        normalized = normalize_domain(domain)
        if not is_valid_domain(normalized):
            return ResolutionResult(
                domain=None, account_id=None,
                confidence=ResolutionConfidence.UNRESOLVABLE,
                strategy="bare_domain",
                reason=f"Invalid domain: {normalized!r}",
            )
        if is_free_email_domain(normalized):
            return ResolutionResult(
                domain=None, account_id=None,
                confidence=ResolutionConfidence.UNRESOLVABLE,
                strategy="bare_domain",
                reason=f"Free email domain: {normalized!r}",
            )
        return ResolutionResult(
            domain=normalized, account_id=None,
            confidence=ResolutionConfidence.HIGH,
            strategy="bare_domain",
        )


# ---------------------------------------------------------------------------
# Async multi-strategy resolver (Sprint 3)
# ---------------------------------------------------------------------------


class AsyncAccountResolver:
    """Full multi-strategy account resolver with DB, alias, and enrichment support.

    Strategy waterfall (ADR 0005):
    1. explicit_domain  → HIGH  (trust the caller)
    2. email domain     → HIGH  (business email) / UNRESOLVABLE (free/invalid)
    3. alias table      → HIGH  (acquired/rebranded domain)
    4. CRM company-ID   → MEDIUM
    5. IP-to-company    → MEDIUM (confidence ≥ 0.7) or LOW (< 0.7)
    6. → UNRESOLVABLE

    Inject stubs for all dependencies to keep unit tests fast and DB-free.
    """

    # Confidence threshold for IP resolution to qualify as MEDIUM (not LOW)
    IP_MEDIUM_THRESHOLD: float = 0.70

    def __init__(
        self,
        account_repo: "AccountRepository",
        firmographic_enricher: "BaseEnricher | None" = None,
        ip_enricher: "BaseIPEnricher | None" = None,
    ) -> None:
        self._repo = account_repo
        self._firmographic = firmographic_enricher
        self._ip = ip_enricher

    async def resolve(self, signal: Any) -> ResolutionResult:
        """Run all strategies in waterfall order and return the first actionable result.

        Args:
            signal: ResolutionInput (imported lazily to avoid circular imports).

        Returns:
            ResolutionResult with the best achievable confidence.
        """
        from identity.models import ResolutionInput  # lazy import avoids circular dep

        inp: ResolutionInput = signal

        # ------------------------------------------------------------------
        # Strategy 1: explicit_domain (caller-supplied, unconditional trust)
        # ------------------------------------------------------------------
        if inp.explicit_domain:
            domain = normalize_domain(inp.explicit_domain)
            account_id = await self._ensure_account(domain)
            return ResolutionResult(
                domain=domain, account_id=account_id,
                confidence=ResolutionConfidence.HIGH,
                strategy="explicit_domain",
            )

        # ------------------------------------------------------------------
        # Strategy 2: email domain
        # ------------------------------------------------------------------
        if inp.email:
            domain = normalize_domain(inp.email)
            if is_valid_domain(domain) and not is_free_email_domain(domain):
                # Check alias table before accepting the raw domain
                alias_result = await self._try_alias(domain)
                if alias_result is not None:
                    logger.debug("Alias resolved %s → %s", domain, alias_result)
                    account_id = await self._ensure_account(alias_result)
                    return ResolutionResult(
                        domain=alias_result, account_id=account_id,
                        confidence=ResolutionConfidence.HIGH,
                        strategy="alias_table",
                    )
                account_id = await self._ensure_account(domain)
                return ResolutionResult(
                    domain=domain, account_id=account_id,
                    confidence=ResolutionConfidence.HIGH,
                    strategy="email_domain",
                )

            if is_free_email_domain(domain):
                logger.debug("Free email domain: %s — trying fallback strategies", domain)
                # Fall through to IP / CRM strategies (do not return yet)

        # ------------------------------------------------------------------
        # Strategy 3: CRM company-ID cross-reference
        # ------------------------------------------------------------------
        if inp.crm_company_id and inp.crm_source:
            xref = await self._repo.get_by_crm_id(inp.crm_source, inp.crm_company_id)
            if xref is not None:
                account_id = await self._ensure_account(xref.canonical_domain)
                return ResolutionResult(
                    domain=xref.canonical_domain, account_id=account_id,
                    confidence=ResolutionConfidence.MEDIUM,
                    strategy="crm_xref",
                )

        # ------------------------------------------------------------------
        # Strategy 4: IP-to-company enrichment
        # ------------------------------------------------------------------
        if inp.ip_address and self._ip is not None:
            ip_result = await self._ip.enrich_by_ip(inp.ip_address)
            if ip_result is not None and ip_result.domain:
                alias_result = await self._try_alias(ip_result.domain)
                resolved_domain = alias_result or ip_result.domain
                if is_valid_domain(resolved_domain) and not is_free_email_domain(resolved_domain):
                    account_id = await self._ensure_account(resolved_domain)
                    confidence = (
                        ResolutionConfidence.MEDIUM
                        if ip_result.confidence >= self.IP_MEDIUM_THRESHOLD
                        else ResolutionConfidence.LOW
                    )
                    return ResolutionResult(
                        domain=resolved_domain, account_id=account_id,
                        confidence=confidence,
                        strategy="ip_enrichment",
                        reason=f"IP confidence={ip_result.confidence:.2f} source={ip_result.source}",
                    )

        # ------------------------------------------------------------------
        # Unresolvable
        # ------------------------------------------------------------------
        return ResolutionResult(
            domain=None, account_id=None,
            confidence=ResolutionConfidence.UNRESOLVABLE,
            strategy="exhausted",
            reason="No strategy produced a resolvable domain",
        )

    async def _try_alias(self, domain: str) -> str | None:
        """Check the domain alias table; return canonical domain or None."""
        alias = await self._repo.get_alias(domain)
        if alias is not None and alias.is_active:
            return alias.canonical_domain
        return None

    async def _ensure_account(self, domain: str) -> str | None:
        """Look up account by domain; create if not found. Returns account UUID."""
        account = await self._repo.get_by_domain(domain)
        if account is not None:
            return account.id
        try:
            created = await self._repo.create_account(domain)
            return created.id
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not create account for domain=%s: %s", domain, exc)
            return None


# ---------------------------------------------------------------------------
# Committee member resolver (sync — no DB; DB version in CommitteeMemberRepository)
# ---------------------------------------------------------------------------


class CommitteeMemberResolver:
    """Classifies committee member attributes from raw signal data.

    Stateless — does not touch the database. Database persistence is handled
    by CommitteeMemberRepository (identity.repository).
    """

    def infer_seniority(self, title: str | None) -> Any:
        """Infer SeniorityLevel from a job title string."""
        from identity.models import infer_seniority
        return infer_seniority(title)

    def compute_role_weight(self, title: str | None) -> float:
        """Compute numeric role weight (0.0–1.0) from a job title."""
        from identity.models import ROLE_WEIGHTS, infer_seniority
        level = infer_seniority(title)
        return ROLE_WEIGHTS[level]

    def extract_department(self, title: str | None) -> str | None:
        """Best-effort department extraction from a job title."""
        if not title:
            return None
        title_lower = title.lower()
        dept_keywords: dict[str, str] = {
            "finance": "Finance", "revenue": "Revenue", "sales": "Sales",
            "marketing": "Marketing", "engineering": "Engineering",
            "product": "Product", "operations": "Operations",
            "procurement": "Procurement", "legal": "Legal", "it ": "IT",
        }
        for keyword, dept in dept_keywords.items():
            if keyword in title_lower:
                return dept
        return None
