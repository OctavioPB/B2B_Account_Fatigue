"""Unit tests for identity.resolver — normalize_domain(), AccountResolver, AsyncAccountResolver.

Run: pytest identity/tests/ -v
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from identity.models import (
    Account,
    CRMAccountXRef,
    DomainAlias,
    FirmographicData,
    IPResolutionData,
    ResolutionInput,
)
from identity.resolver import (
    AccountResolver,
    AsyncAccountResolver,
    CommitteeMemberResolver,
    ResolutionConfidence,
    ResolutionResult,
    extract_domain_from_email,
    is_free_email_domain,
    is_valid_domain,
    normalize_domain,
)


# ---------------------------------------------------------------------------
# Helpers — minimal repo stubs
# ---------------------------------------------------------------------------


def _make_account(domain: str) -> Account:
    return Account(id=str(uuid.uuid4()), domain=domain)


def _make_alias(alias: str, canonical: str) -> DomainAlias:
    return DomainAlias(id=str(uuid.uuid4()), alias_domain=alias, canonical_domain=canonical)


def _make_crm_xref(domain: str, crm_source: str, crm_id: str) -> CRMAccountXRef:
    return CRMAccountXRef(
        id=str(uuid.uuid4()),
        canonical_domain=domain,
        crm_source=crm_source,
        crm_company_id=crm_id,
    )


def _make_account_repo(
    domain_accounts: dict[str, Account] | None = None,
    alias_map: dict[str, DomainAlias] | None = None,
    crm_map: dict[tuple[str, str], CRMAccountXRef] | None = None,
) -> MagicMock:
    repo = MagicMock()
    domain_accounts = domain_accounts or {}
    alias_map = alias_map or {}
    crm_map = crm_map or {}

    async def _get_by_domain(domain: str) -> Account | None:
        return domain_accounts.get(domain)

    async def _create_account(domain: str) -> Account:
        acc = _make_account(domain)
        domain_accounts[domain] = acc
        return acc

    async def _get_alias(alias_domain: str) -> DomainAlias | None:
        return alias_map.get(alias_domain)

    async def _get_by_crm_id(crm_source: str, crm_company_id: str) -> CRMAccountXRef | None:
        return crm_map.get((crm_source, crm_company_id))

    repo.get_by_domain = _get_by_domain
    repo.create_account = _create_account
    repo.get_alias = _get_alias
    repo.get_by_crm_id = _get_by_crm_id
    return repo


def _make_ip_enricher(
    results: dict[str, IPResolutionData | None] | None = None,
) -> MagicMock:
    enricher = MagicMock()
    results = results or {}

    async def _enrich_by_ip(ip: str) -> IPResolutionData | None:
        return results.get(ip)

    enricher.enrich_by_ip = _enrich_by_ip
    return enricher


# ---------------------------------------------------------------------------
# normalize_domain
# ---------------------------------------------------------------------------
class TestNormalizeDomain:
    @pytest.mark.unit
    def test_extracts_domain_from_email(self) -> None:
        assert normalize_domain("alice@acme.com") == "acme.com"

    @pytest.mark.unit
    def test_lowercases_domain(self) -> None:
        assert normalize_domain("ALICE@ACME.COM") == "acme.com"

    @pytest.mark.unit
    def test_strips_www_prefix(self) -> None:
        assert normalize_domain("www.acme.com") == "acme.com"

    @pytest.mark.unit
    def test_bare_domain_passthrough(self) -> None:
        assert normalize_domain("acme.com") == "acme.com"

    @pytest.mark.unit
    def test_strips_leading_whitespace(self) -> None:
        assert normalize_domain("  alice@acme.com  ") == "acme.com"

    @pytest.mark.unit
    def test_subdomain_preserved(self) -> None:
        # Only www. is stripped; other subdomains are kept as-is
        assert normalize_domain("alice@mail.acme.com") == "mail.acme.com"

    @pytest.mark.unit
    def test_no_at_sign_treated_as_domain(self) -> None:
        assert normalize_domain("acme.com") == "acme.com"


# ---------------------------------------------------------------------------
# is_free_email_domain
# ---------------------------------------------------------------------------
class TestIsFreeEmailDomain:
    @pytest.mark.unit
    @pytest.mark.parametrize(
        "domain",
        ["gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com", "protonmail.com"],
    )
    def test_known_free_domains(self, domain: str) -> None:
        assert is_free_email_domain(domain) is True

    @pytest.mark.unit
    def test_company_domain_is_not_free(self) -> None:
        assert is_free_email_domain("acme.com") is False

    @pytest.mark.unit
    def test_email_with_free_domain(self) -> None:
        assert is_free_email_domain("user@gmail.com") is True


# ---------------------------------------------------------------------------
# is_valid_domain
# ---------------------------------------------------------------------------
class TestIsValidDomain:
    @pytest.mark.unit
    def test_valid_domain(self) -> None:
        assert is_valid_domain("acme.com") is True

    @pytest.mark.unit
    def test_valid_subdomain(self) -> None:
        assert is_valid_domain("mail.acme.co.uk") is True

    @pytest.mark.unit
    def test_rejects_empty_string(self) -> None:
        assert is_valid_domain("") is False

    @pytest.mark.unit
    def test_rejects_no_tld(self) -> None:
        assert is_valid_domain("acme") is False


# ---------------------------------------------------------------------------
# AccountResolver
# ---------------------------------------------------------------------------
class TestAccountResolver:
    @pytest.fixture
    def resolver(self) -> AccountResolver:
        return AccountResolver()

    @pytest.mark.unit
    def test_resolves_business_email(self, resolver: AccountResolver) -> None:
        result = resolver.resolve_from_email("cfo@acme.com")
        assert result.domain == "acme.com"
        assert result.confidence == ResolutionConfidence.HIGH
        assert result.strategy == "email_domain"

    @pytest.mark.unit
    def test_quarantines_free_email(self, resolver: AccountResolver) -> None:
        result = resolver.resolve_from_email("personal@gmail.com")
        assert result.domain is None
        assert result.confidence == ResolutionConfidence.UNRESOLVABLE

    @pytest.mark.unit
    def test_resolves_bare_domain(self, resolver: AccountResolver) -> None:
        result = resolver.resolve_from_domain("acme.com")
        assert result.domain == "acme.com"
        assert result.confidence == ResolutionConfidence.HIGH

    @pytest.mark.unit
    def test_bare_domain_strips_www(self, resolver: AccountResolver) -> None:
        result = resolver.resolve_from_domain("www.acme.com")
        assert result.domain == "acme.com"

    @pytest.mark.unit
    def test_unresolvable_for_invalid_domain(self, resolver: AccountResolver) -> None:
        result = resolver.resolve_from_email("user@notadomain")
        assert result.domain is None
        assert result.confidence == ResolutionConfidence.UNRESOLVABLE


# ---------------------------------------------------------------------------
# extract_domain_from_email
# ---------------------------------------------------------------------------


class TestExtractDomainFromEmail:
    @pytest.mark.parametrize(
        "email, expected",
        [
            ("cfo@acme.com", "acme.com"),
            ("user@GLOBEX.COM", "globex.com"),
            ("user@gmail.com", None),          # free email
            ("user@notadomain", None),          # invalid
            ("someone@proton.me", None),        # free email
        ],
    )
    def test_extract(self, email: str, expected: str | None) -> None:
        assert extract_domain_from_email(email) == expected


# ---------------------------------------------------------------------------
# ResolutionResult helpers
# ---------------------------------------------------------------------------


class TestResolutionResult:
    def test_high_is_actionable(self) -> None:
        r = ResolutionResult(domain="a.com", account_id=None, confidence=ResolutionConfidence.HIGH, strategy="s")
        assert r.is_actionable() is True
        assert r.needs_quarantine() is False

    def test_medium_is_actionable(self) -> None:
        r = ResolutionResult(domain="a.com", account_id=None, confidence=ResolutionConfidence.MEDIUM, strategy="s")
        assert r.is_actionable() is True
        assert r.needs_quarantine() is False

    def test_low_needs_quarantine(self) -> None:
        r = ResolutionResult(domain=None, account_id=None, confidence=ResolutionConfidence.LOW, strategy="s")
        assert r.is_actionable() is False
        assert r.needs_quarantine() is True

    def test_unresolvable_needs_quarantine(self) -> None:
        r = ResolutionResult(domain=None, account_id=None, confidence=ResolutionConfidence.UNRESOLVABLE, strategy="s")
        assert r.is_actionable() is False
        assert r.needs_quarantine() is True


# ---------------------------------------------------------------------------
# AsyncAccountResolver — Strategy 1: explicit_domain
# ---------------------------------------------------------------------------


class TestAsyncResolverExplicitDomain:
    @pytest.mark.asyncio
    async def test_explicit_domain_returns_high(self) -> None:
        repo = _make_account_repo()
        resolver = AsyncAccountResolver(account_repo=repo)
        result = await resolver.resolve(
            ResolutionInput(explicit_domain="acme.com", source_event_id="t1", source_topic="t")
        )
        assert result.confidence == ResolutionConfidence.HIGH
        assert result.domain == "acme.com"
        assert result.strategy == "explicit_domain"

    @pytest.mark.asyncio
    async def test_explicit_domain_normalizes(self) -> None:
        repo = _make_account_repo()
        resolver = AsyncAccountResolver(account_repo=repo)
        result = await resolver.resolve(
            ResolutionInput(explicit_domain="www.ACME.COM", source_event_id="t2", source_topic="t")
        )
        assert result.domain == "acme.com"

    @pytest.mark.asyncio
    async def test_explicit_domain_creates_account_if_missing(self) -> None:
        repo = _make_account_repo()
        resolver = AsyncAccountResolver(account_repo=repo)
        result = await resolver.resolve(
            ResolutionInput(explicit_domain="new-corp.com", source_event_id="t3", source_topic="t")
        )
        assert result.account_id is not None

    @pytest.mark.asyncio
    async def test_explicit_domain_reuses_existing_account(self) -> None:
        existing = _make_account("existing.com")
        repo = _make_account_repo(domain_accounts={"existing.com": existing})
        resolver = AsyncAccountResolver(account_repo=repo)
        result = await resolver.resolve(
            ResolutionInput(explicit_domain="existing.com", source_event_id="t4", source_topic="t")
        )
        assert result.account_id == existing.id


# ---------------------------------------------------------------------------
# AsyncAccountResolver — Strategy 2: email_domain
# ---------------------------------------------------------------------------


class TestAsyncResolverEmailDomain:
    @pytest.mark.asyncio
    async def test_business_email_high(self) -> None:
        repo = _make_account_repo()
        resolver = AsyncAccountResolver(account_repo=repo)
        result = await resolver.resolve(
            ResolutionInput(email="cto@acme.com", source_event_id="e1", source_topic="t")
        )
        assert result.confidence == ResolutionConfidence.HIGH
        assert result.domain == "acme.com"
        assert result.strategy == "email_domain"

    @pytest.mark.asyncio
    async def test_free_email_falls_through(self) -> None:
        """Free email without fallback → UNRESOLVABLE."""
        repo = _make_account_repo()
        resolver = AsyncAccountResolver(account_repo=repo)
        result = await resolver.resolve(
            ResolutionInput(email="user@gmail.com", source_event_id="e2", source_topic="t")
        )
        assert result.confidence == ResolutionConfidence.UNRESOLVABLE

    @pytest.mark.asyncio
    async def test_invalid_email_domain_unresolvable(self) -> None:
        repo = _make_account_repo()
        resolver = AsyncAccountResolver(account_repo=repo)
        result = await resolver.resolve(
            ResolutionInput(email="user@notadomain", source_event_id="e3", source_topic="t")
        )
        assert result.confidence == ResolutionConfidence.UNRESOLVABLE

    @pytest.mark.asyncio
    async def test_email_alias_resolves_to_canonical(self) -> None:
        alias = _make_alias("old-acme.com", "acme.com")
        repo = _make_account_repo(alias_map={"old-acme.com": alias})
        resolver = AsyncAccountResolver(account_repo=repo)
        result = await resolver.resolve(
            ResolutionInput(email="cfo@old-acme.com", source_event_id="e4", source_topic="t")
        )
        assert result.domain == "acme.com"
        assert result.strategy == "alias_table"
        assert result.confidence == ResolutionConfidence.HIGH

    @pytest.mark.asyncio
    async def test_email_no_alias_uses_raw_domain(self) -> None:
        repo = _make_account_repo()
        resolver = AsyncAccountResolver(account_repo=repo)
        result = await resolver.resolve(
            ResolutionInput(email="user@globex.com", source_event_id="e5", source_topic="t")
        )
        assert result.domain == "globex.com"
        assert result.strategy == "email_domain"

    @pytest.mark.asyncio
    async def test_proton_me_is_free_email(self) -> None:
        repo = _make_account_repo()
        resolver = AsyncAccountResolver(account_repo=repo)
        result = await resolver.resolve(
            ResolutionInput(email="user@proton.me", source_event_id="e6", source_topic="t")
        )
        assert result.confidence == ResolutionConfidence.UNRESOLVABLE


# ---------------------------------------------------------------------------
# AsyncAccountResolver — Strategy 3: CRM cross-reference
# ---------------------------------------------------------------------------


class TestAsyncResolverCRMXRef:
    @pytest.mark.asyncio
    async def test_crm_resolves_free_email(self) -> None:
        xref = _make_crm_xref("acme.com", "HUBSPOT", "hs-001")
        repo = _make_account_repo(crm_map={("HUBSPOT", "hs-001"): xref})
        resolver = AsyncAccountResolver(account_repo=repo)
        result = await resolver.resolve(
            ResolutionInput(
                email="user@gmail.com",
                crm_company_id="hs-001",
                crm_source="HUBSPOT",
                source_event_id="c1",
                source_topic="t",
            )
        )
        assert result.domain == "acme.com"
        assert result.confidence == ResolutionConfidence.MEDIUM
        assert result.strategy == "crm_xref"

    @pytest.mark.asyncio
    async def test_crm_miss_continues_waterfall(self) -> None:
        repo = _make_account_repo()
        resolver = AsyncAccountResolver(account_repo=repo)
        result = await resolver.resolve(
            ResolutionInput(
                email="user@gmail.com",
                crm_company_id="nonexistent",
                crm_source="HUBSPOT",
                source_event_id="c2",
                source_topic="t",
            )
        )
        # No IP enricher → falls through to UNRESOLVABLE
        assert result.confidence == ResolutionConfidence.UNRESOLVABLE

    @pytest.mark.asyncio
    async def test_crm_only_tried_when_both_source_and_id_present(self) -> None:
        xref = _make_crm_xref("acme.com", "HUBSPOT", "hs-001")
        repo = _make_account_repo(crm_map={("HUBSPOT", "hs-001"): xref})
        resolver = AsyncAccountResolver(account_repo=repo)
        # crm_source missing → CRM strategy skipped
        result = await resolver.resolve(
            ResolutionInput(
                email="user@gmail.com",
                crm_company_id="hs-001",
                crm_source=None,  # missing
                source_event_id="c3",
                source_topic="t",
            )
        )
        assert result.confidence == ResolutionConfidence.UNRESOLVABLE


# ---------------------------------------------------------------------------
# AsyncAccountResolver — Strategy 4: IP enrichment
# ---------------------------------------------------------------------------


class TestAsyncResolverIPEnrichment:
    @pytest.mark.asyncio
    async def test_high_confidence_ip_is_medium(self) -> None:
        ip_data = IPResolutionData(ip_address="1.2.3.4", domain="acme.com", confidence=0.90, source="stub")
        ip_enricher = _make_ip_enricher({"1.2.3.4": ip_data})
        repo = _make_account_repo()
        resolver = AsyncAccountResolver(account_repo=repo, ip_enricher=ip_enricher)
        result = await resolver.resolve(
            ResolutionInput(ip_address="1.2.3.4", source_event_id="ip1", source_topic="t")
        )
        assert result.domain == "acme.com"
        assert result.confidence == ResolutionConfidence.MEDIUM
        assert result.strategy == "ip_enrichment"

    @pytest.mark.asyncio
    async def test_low_confidence_ip_is_low(self) -> None:
        ip_data = IPResolutionData(ip_address="5.6.7.8", domain="maybe.com", confidence=0.50, source="stub")
        ip_enricher = _make_ip_enricher({"5.6.7.8": ip_data})
        repo = _make_account_repo()
        resolver = AsyncAccountResolver(account_repo=repo, ip_enricher=ip_enricher)
        result = await resolver.resolve(
            ResolutionInput(ip_address="5.6.7.8", source_event_id="ip2", source_topic="t")
        )
        assert result.confidence == ResolutionConfidence.LOW
        assert result.domain == "maybe.com"

    @pytest.mark.asyncio
    async def test_ip_at_medium_threshold_is_medium(self) -> None:
        ip_data = IPResolutionData(ip_address="9.9.9.9", domain="threshold.com", confidence=0.70, source="stub")
        ip_enricher = _make_ip_enricher({"9.9.9.9": ip_data})
        repo = _make_account_repo()
        resolver = AsyncAccountResolver(account_repo=repo, ip_enricher=ip_enricher)
        result = await resolver.resolve(
            ResolutionInput(ip_address="9.9.9.9", source_event_id="ip3", source_topic="t")
        )
        assert result.confidence == ResolutionConfidence.MEDIUM

    @pytest.mark.asyncio
    async def test_ip_with_alias_resolves_to_canonical(self) -> None:
        ip_data = IPResolutionData(ip_address="2.2.2.2", domain="old-brand.com", confidence=0.85, source="stub")
        ip_enricher = _make_ip_enricher({"2.2.2.2": ip_data})
        alias = _make_alias("old-brand.com", "newbrand.com")
        repo = _make_account_repo(alias_map={"old-brand.com": alias})
        resolver = AsyncAccountResolver(account_repo=repo, ip_enricher=ip_enricher)
        result = await resolver.resolve(
            ResolutionInput(ip_address="2.2.2.2", source_event_id="ip4", source_topic="t")
        )
        assert result.domain == "newbrand.com"

    @pytest.mark.asyncio
    async def test_ip_enricher_returns_none_is_unresolvable(self) -> None:
        ip_enricher = _make_ip_enricher({})
        repo = _make_account_repo()
        resolver = AsyncAccountResolver(account_repo=repo, ip_enricher=ip_enricher)
        result = await resolver.resolve(
            ResolutionInput(ip_address="0.0.0.0", source_event_id="ip5", source_topic="t")
        )
        assert result.confidence == ResolutionConfidence.UNRESOLVABLE

    @pytest.mark.asyncio
    async def test_no_ip_enricher_skips_ip_strategy(self) -> None:
        repo = _make_account_repo()
        resolver = AsyncAccountResolver(account_repo=repo, ip_enricher=None)
        result = await resolver.resolve(
            ResolutionInput(ip_address="1.2.3.4", source_event_id="ip6", source_topic="t")
        )
        assert result.confidence == ResolutionConfidence.UNRESOLVABLE

    @pytest.mark.asyncio
    async def test_ip_with_free_email_domain_skipped(self) -> None:
        # IP result that resolves to a free-email domain should not be accepted
        ip_data = IPResolutionData(ip_address="3.3.3.3", domain="gmail.com", confidence=0.95, source="stub")
        ip_enricher = _make_ip_enricher({"3.3.3.3": ip_data})
        repo = _make_account_repo()
        resolver = AsyncAccountResolver(account_repo=repo, ip_enricher=ip_enricher)
        result = await resolver.resolve(
            ResolutionInput(ip_address="3.3.3.3", source_event_id="ip7", source_topic="t")
        )
        assert result.confidence == ResolutionConfidence.UNRESOLVABLE


# ---------------------------------------------------------------------------
# AsyncAccountResolver — waterfall priority
# ---------------------------------------------------------------------------


class TestAsyncResolverWaterfallPriority:
    @pytest.mark.asyncio
    async def test_explicit_domain_beats_email(self) -> None:
        repo = _make_account_repo()
        resolver = AsyncAccountResolver(account_repo=repo)
        result = await resolver.resolve(
            ResolutionInput(
                explicit_domain="override.com",
                email="user@other.com",
                source_event_id="wf1",
                source_topic="t",
            )
        )
        assert result.domain == "override.com"
        assert result.strategy == "explicit_domain"

    @pytest.mark.asyncio
    async def test_email_beats_crm(self) -> None:
        xref = _make_crm_xref("crm-domain.com", "HUBSPOT", "hs-1")
        repo = _make_account_repo(crm_map={("HUBSPOT", "hs-1"): xref})
        resolver = AsyncAccountResolver(account_repo=repo)
        result = await resolver.resolve(
            ResolutionInput(
                email="user@business.com",  # valid business email → resolves immediately
                crm_company_id="hs-1",
                crm_source="HUBSPOT",
                source_event_id="wf2",
                source_topic="t",
            )
        )
        # email_domain strategy resolves before CRM is tried
        assert result.strategy == "email_domain"
        assert result.domain == "business.com"

    @pytest.mark.asyncio
    async def test_all_strategies_exhausted_returns_unresolvable(self) -> None:
        repo = _make_account_repo()
        resolver = AsyncAccountResolver(account_repo=repo)
        result = await resolver.resolve(
            ResolutionInput(source_event_id="wf3", source_topic="t")
        )
        assert result.confidence == ResolutionConfidence.UNRESOLVABLE
        assert result.strategy == "exhausted"


# ---------------------------------------------------------------------------
# CommitteeMemberResolver
# ---------------------------------------------------------------------------


class TestCommitteeMemberResolver:
    @pytest.fixture
    def resolver(self) -> CommitteeMemberResolver:
        return CommitteeMemberResolver()

    def test_infer_seniority_ceo(self, resolver: CommitteeMemberResolver) -> None:
        from identity.models import SeniorityLevel
        assert resolver.infer_seniority("CEO") == SeniorityLevel.C_SUITE

    def test_compute_role_weight_c_suite(self, resolver: CommitteeMemberResolver) -> None:
        weight = resolver.compute_role_weight("Chief Financial Officer")
        assert weight == pytest.approx(1.0)

    def test_compute_role_weight_ic(self, resolver: CommitteeMemberResolver) -> None:
        weight = resolver.compute_role_weight("Software Engineer")
        assert weight == pytest.approx(0.2)

    @pytest.mark.parametrize(
        "title, expected_dept",
        [
            ("VP Finance", "Finance"),
            ("Director of Sales", "Sales"),
            ("Marketing Manager", "Marketing"),
            ("Chief Engineering Officer", "Engineering"),
            ("Product Lead", "Product"),
            ("Legal Counsel", "Legal"),
            ("IT Director", "IT"),
            ("Random Person", None),
            (None, None),
        ],
    )
    def test_extract_department(
        self, resolver: CommitteeMemberResolver, title: str | None, expected_dept: str | None
    ) -> None:
        assert resolver.extract_department(title) == expected_dept
