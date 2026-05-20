"""Tests for identity.models — seniority inference, role weights, and domain entities."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from identity.models import (
    ROLE_WEIGHTS,
    AliasType,
    ArrBand,
    CommitteeMember,
    DomainAlias,
    FirmographicData,
    IPResolutionData,
    ResolutionInput,
    SeniorityLevel,
    infer_seniority,
)


# ---------------------------------------------------------------------------
# infer_seniority
# ---------------------------------------------------------------------------


class TestInferSeniority:
    @pytest.mark.parametrize(
        "title, expected",
        [
            ("Chief Executive Officer", SeniorityLevel.C_SUITE),
            ("CEO", SeniorityLevel.C_SUITE),
            ("cfo", SeniorityLevel.C_SUITE),
            ("Chief Technology Officer", SeniorityLevel.C_SUITE),
            ("Founder & CEO", SeniorityLevel.C_SUITE),
            ("President", SeniorityLevel.C_SUITE),
            ("Owner", SeniorityLevel.C_SUITE),
            ("CISO", SeniorityLevel.C_SUITE),
            ("VP of Sales", SeniorityLevel.VP),
            ("Vice President, Marketing", SeniorityLevel.VP),
            ("SVP Revenue Operations", SeniorityLevel.VP),
            ("EVP Engineering", SeniorityLevel.VP),
            ("Director of Product", SeniorityLevel.DIRECTOR),
            ("Head of Engineering", SeniorityLevel.DIRECTOR),
            ("Principal Engineer", SeniorityLevel.DIRECTOR),
            ("Engineering Manager", SeniorityLevel.MANAGER),
            ("Senior Software Engineer", SeniorityLevel.MANAGER),
            ("Team Lead", SeniorityLevel.MANAGER),
            ("Sr. Developer", SeniorityLevel.MANAGER),
            ("Software Engineer", SeniorityLevel.IC),
            ("Account Executive", SeniorityLevel.IC),
            ("Sales Representative", SeniorityLevel.IC),
            (None, SeniorityLevel.IC),
            ("", SeniorityLevel.IC),
            ("   ", SeniorityLevel.IC),
        ],
    )
    def test_infer_seniority(self, title: str | None, expected: SeniorityLevel) -> None:
        assert infer_seniority(title) == expected

    def test_c_suite_beats_manager_keywords(self) -> None:
        # "Chief" should win over any MANAGER-tier keywords in the same title
        assert infer_seniority("Chief of Staff") == SeniorityLevel.C_SUITE

    def test_vp_beats_director(self) -> None:
        assert infer_seniority("VP of Director Relations") == SeniorityLevel.VP


# ---------------------------------------------------------------------------
# ROLE_WEIGHTS
# ---------------------------------------------------------------------------


class TestRoleWeights:
    def test_all_seniority_levels_have_weight(self) -> None:
        for level in SeniorityLevel:
            assert level in ROLE_WEIGHTS

    def test_weights_are_ordered(self) -> None:
        assert (
            ROLE_WEIGHTS[SeniorityLevel.C_SUITE]
            > ROLE_WEIGHTS[SeniorityLevel.VP]
            > ROLE_WEIGHTS[SeniorityLevel.DIRECTOR]
            > ROLE_WEIGHTS[SeniorityLevel.MANAGER]
            > ROLE_WEIGHTS[SeniorityLevel.IC]
        )

    def test_weights_in_range(self) -> None:
        for weight in ROLE_WEIGHTS.values():
            assert 0.0 <= weight <= 1.0

    def test_c_suite_is_max(self) -> None:
        assert ROLE_WEIGHTS[SeniorityLevel.C_SUITE] == 1.0

    def test_ic_is_min(self) -> None:
        assert ROLE_WEIGHTS[SeniorityLevel.IC] == pytest.approx(0.2)


# ---------------------------------------------------------------------------
# DomainAlias.is_active
# ---------------------------------------------------------------------------


class TestDomainAliasIsActive:
    def _make_alias(
        self,
        effective_from: datetime | None = None,
        effective_to: datetime | None = None,
    ) -> DomainAlias:
        now = datetime.now(timezone.utc)
        return DomainAlias(
            id="test-id",
            alias_domain="old.com",
            canonical_domain="new.com",
            alias_type=AliasType.REBRAND,
            effective_from=effective_from or now - timedelta(days=1),
            effective_to=effective_to,
        )

    def test_active_when_no_effective_to(self) -> None:
        alias = self._make_alias(effective_to=None)
        assert alias.is_active is True

    def test_active_when_effective_to_in_future(self) -> None:
        alias = self._make_alias(effective_to=datetime.now(timezone.utc) + timedelta(days=30))
        assert alias.is_active is True

    def test_inactive_when_effective_to_in_past(self) -> None:
        alias = self._make_alias(effective_to=datetime.now(timezone.utc) - timedelta(hours=1))
        assert alias.is_active is False

    def test_inactive_when_effective_from_in_future(self) -> None:
        alias = self._make_alias(
            effective_from=datetime.now(timezone.utc) + timedelta(days=1),
            effective_to=None,
        )
        assert alias.is_active is False


# ---------------------------------------------------------------------------
# CommitteeMember.display_name
# ---------------------------------------------------------------------------


class TestCommitteeMemberDisplayName:
    def _make_member(self, **kwargs) -> CommitteeMember:  # type: ignore[no-untyped-def]
        defaults = {
            "id": "mid",
            "account_id": "aid",
            "email": "john.doe@acme.com",
        }
        return CommitteeMember(**{**defaults, **kwargs})

    def test_full_name(self) -> None:
        m = self._make_member(first_name="John", last_name="Doe")
        assert m.display_name() == "John Doe"

    def test_first_name_only(self) -> None:
        m = self._make_member(first_name="Alice", last_name=None)
        assert m.display_name() == "Alice"

    def test_last_name_only(self) -> None:
        m = self._make_member(first_name=None, last_name="Smith")
        assert m.display_name() == "Smith"

    def test_falls_back_to_email_prefix(self) -> None:
        m = self._make_member(first_name=None, last_name=None)
        assert m.display_name() == "john.doe"


# ---------------------------------------------------------------------------
# FirmographicData defaults
# ---------------------------------------------------------------------------


class TestFirmographicData:
    def test_source_defaults_to_unknown(self) -> None:
        fd = FirmographicData(domain="test.com")
        assert fd.source == "unknown"

    def test_raw_defaults_to_empty_dict(self) -> None:
        fd = FirmographicData(domain="test.com")
        assert fd.raw == {}

    def test_enriched_at_is_set(self) -> None:
        fd = FirmographicData(domain="test.com")
        assert fd.enriched_at is not None


# ---------------------------------------------------------------------------
# IPResolutionData
# ---------------------------------------------------------------------------


class TestIPResolutionData:
    def test_confidence_in_range(self) -> None:
        ip = IPResolutionData(ip_address="1.2.3.4", domain="acme.com", confidence=0.85)
        assert 0.0 <= ip.confidence <= 1.0

    def test_domain_can_be_none(self) -> None:
        ip = IPResolutionData(ip_address="1.2.3.4", domain=None)
        assert ip.domain is None


# ---------------------------------------------------------------------------
# ResolutionInput
# ---------------------------------------------------------------------------


class TestResolutionInput:
    def test_all_fields_optional(self) -> None:
        inp = ResolutionInput()
        assert inp.email is None
        assert inp.ip_address is None
        assert inp.explicit_domain is None

    def test_source_event_id_defaults_empty(self) -> None:
        inp = ResolutionInput()
        assert inp.source_event_id == ""

    def test_raw_context_defaults_empty_dict(self) -> None:
        inp = ResolutionInput()
        assert inp.raw_context == {}
