"""Tests for identity.pipeline — ResolutionPipeline end-to-end accuracy.

Definition of Done (Sprint 3 ADR 0005):
  - ≥ 95% of synthetic events resolve to the expected domain
  - LOW-confidence events route to quarantine, never silently dropped
  - Pipeline latency < 50ms p99 (asserted over 100 events)

All tests use in-memory mock repositories — no database required.
"""

from __future__ import annotations

import asyncio
import statistics
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from identity.models import (
    Account,
    CommitteeMember,
    CRMAccountXRef,
    DomainAlias,
    FirmographicData,
    IPResolutionData,
    ResolutionInput,
    SeniorityLevel,
)
from identity.pipeline import EnrichedEvent, ResolutionPipeline
from identity.quarantine import QuarantineQueue
from identity.resolver import AsyncAccountResolver, ResolutionConfidence
from identity.tests.fixtures.synthetic_events import make_synthetic_dataset


# ---------------------------------------------------------------------------
# In-memory stub repositories
# ---------------------------------------------------------------------------


class InMemoryAccountRepo:
    """Minimal in-memory AccountRepository stub."""

    def __init__(
        self,
        alias_map: dict[str, str] | None = None,
        crm_map: dict[tuple[str, str], str] | None = None,
    ) -> None:
        self._accounts: dict[str, Account] = {}
        self._aliases: dict[str, str] = alias_map or {}
        self._crm: dict[tuple[str, str], CRMAccountXRef] = {}
        if crm_map:
            for (src, cid), domain in crm_map.items():
                self._crm[(src, cid)] = CRMAccountXRef(
                    id=str(uuid.uuid4()),
                    canonical_domain=domain,
                    crm_source=src,
                    crm_company_id=cid,
                )

    async def get_by_domain(self, domain: str) -> Account | None:
        return self._accounts.get(domain)

    async def get_by_id(self, account_id: str) -> Account | None:
        for acc in self._accounts.values():
            if acc.id == account_id:
                return acc
        return None

    async def create_account(self, domain: str) -> Account:
        acc = Account(id=str(uuid.uuid4()), domain=domain)
        self._accounts[domain] = acc
        return acc

    async def update_firmographic(self, domain: str, data: FirmographicData) -> Account | None:
        acc = self._accounts.get(domain)
        if acc:
            acc.name = data.name
            acc.firmographic_enriched_at = data.enriched_at
        return acc

    async def get_alias(self, alias_domain: str) -> DomainAlias | None:
        canonical = self._aliases.get(alias_domain)
        if canonical is None:
            return None
        return DomainAlias(
            id=str(uuid.uuid4()),
            alias_domain=alias_domain,
            canonical_domain=canonical,
        )

    async def upsert_alias(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def get_by_crm_id(self, crm_source: str, crm_company_id: str) -> CRMAccountXRef | None:
        return self._crm.get((crm_source, crm_company_id))

    async def upsert_crm_xref(self, *args: Any, **kwargs: Any) -> None:
        pass


class InMemoryMemberRepo:
    """Minimal in-memory CommitteeMemberRepository stub."""

    def __init__(self) -> None:
        self._members: dict[tuple[str, str], CommitteeMember] = {}

    async def get_by_email_and_account(self, email: str, account_id: str) -> CommitteeMember | None:
        return self._members.get((email, account_id))

    async def get_members_for_account(
        self, account_id: str, *, active_only: bool = True
    ) -> list[CommitteeMember]:
        return [m for m in self._members.values() if m.account_id == account_id]

    async def upsert_member(
        self,
        account_id: str,
        email: str,
        title: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        crm_contact_id: str | None = None,
        crm_source: str | None = None,
    ) -> CommitteeMember:
        member = CommitteeMember(
            id=str(uuid.uuid4()),
            account_id=account_id,
            email=email,
            title=title,
            first_name=first_name,
            last_name=last_name,
            crm_contact_id=crm_contact_id,
            crm_source=crm_source,
        )
        self._members[(email, account_id)] = member
        return member

    async def touch_last_signal(self, member_id: str) -> None:
        pass


class InMemoryQuarantineRepo:
    """Minimal in-memory QuarantineRepository stub."""

    def __init__(self) -> None:
        self._entries: list[dict[str, Any]] = []

    async def enqueue(
        self,
        event_id: str,
        source_topic: str,
        raw_event: dict[str, Any],
        resolution_attempt: dict[str, Any],
        confidence: str,
    ) -> str:
        qid = str(uuid.uuid4())
        self._entries.append({
            "id": qid,
            "event_id": event_id,
            "source_topic": source_topic,
            "raw_event": raw_event,
            "resolution_attempt": resolution_attempt,
            "confidence": confidence,
            "status": "PENDING",
        })
        return qid

    async def list_pending(self, limit: int = 100) -> list[Any]:
        return [e for e in self._entries if e["status"] == "PENDING"][:limit]

    async def resolve(self, quarantine_id: str, canonical_domain: str, reviewer: str) -> None:
        for e in self._entries:
            if e["id"] == quarantine_id:
                e["status"] = "RESOLVED"
                e["resolved_domain"] = canonical_domain

    async def discard(self, quarantine_id: str, reviewer: str) -> None:
        for e in self._entries:
            if e["id"] == quarantine_id:
                e["status"] = "DISCARDED"


# ---------------------------------------------------------------------------
# IP enricher stub
# ---------------------------------------------------------------------------


class StubIPEnricher:
    """IP enricher backed by the test fixture IP map."""

    def __init__(self, ip_map: dict[str, tuple[str | None, float]]) -> None:
        self._ip_map = ip_map

    @property
    def source_name(self) -> str:
        return "stub"

    async def enrich_by_ip(self, ip_address: str) -> IPResolutionData | None:
        entry = self._ip_map.get(ip_address)
        if entry is None:
            return None
        domain, confidence = entry
        if domain is None:
            return None
        return IPResolutionData(
            ip_address=ip_address,
            domain=domain,
            confidence=confidence,
            source="stub",
        )


# ---------------------------------------------------------------------------
# Pipeline fixture factory
# ---------------------------------------------------------------------------


def make_pipeline(
    alias_map: dict[str, str] | None = None,
    crm_map: dict[tuple[str, str], str] | None = None,
    ip_map: dict[str, tuple[str | None, float]] | None = None,
) -> tuple[ResolutionPipeline, InMemoryQuarantineRepo]:
    account_repo = InMemoryAccountRepo(alias_map=alias_map, crm_map=crm_map)
    member_repo = InMemoryMemberRepo()
    quarantine_repo = InMemoryQuarantineRepo()
    quarantine = QuarantineQueue(quarantine_repo)
    ip_enricher = StubIPEnricher(ip_map or {})
    resolver = AsyncAccountResolver(
        account_repo=account_repo,  # type: ignore[arg-type]
        ip_enricher=ip_enricher,  # type: ignore[arg-type]
    )
    pipeline = ResolutionPipeline(
        resolver=resolver,
        account_repo=account_repo,  # type: ignore[arg-type]
        member_repo=member_repo,  # type: ignore[arg-type]
        quarantine=quarantine,
    )
    return pipeline, quarantine_repo


# ---------------------------------------------------------------------------
# Accuracy test (≥ 95%)
# ---------------------------------------------------------------------------


class TestResolutionAccuracy:
    @pytest.mark.asyncio
    async def test_synthetic_dataset_accuracy(self) -> None:
        """At least 95% of events must resolve to the expected domain."""
        events, alias_map, crm_map, ip_map = make_synthetic_dataset()
        pipeline, _quarantine_repo = make_pipeline(
            alias_map=alias_map,
            crm_map=crm_map,
            ip_map=ip_map,
        )

        correct = 0
        total = len(events)
        failures: list[str] = []

        for synthetic in events:
            raw_event = {"event_id": synthetic.signal.source_event_id}
            enriched = await pipeline.process(
                synthetic.signal,
                raw_event,
                upsert_member=False,
                enrich_new_accounts=False,
            )
            resolved_domain = enriched.domain
            if resolved_domain == synthetic.expected_domain:
                correct += 1
            else:
                failures.append(
                    f"event={synthetic.signal.source_event_id!r} "
                    f"expected={synthetic.expected_domain!r} "
                    f"got={resolved_domain!r} "
                    f"strategy={enriched.resolution.strategy}"
                )

        accuracy = correct / total
        assert accuracy >= 0.95, (
            f"Resolution accuracy {accuracy:.1%} < 95% target.\n"
            f"Failures ({len(failures)}):\n" + "\n".join(failures[:20])
        )

    @pytest.mark.asyncio
    async def test_low_confidence_events_quarantined(self) -> None:
        """LOW-confidence IP events must be quarantined, not silently dropped."""
        _events, alias_map, crm_map, ip_map = make_synthetic_dataset()
        pipeline, quarantine_repo = make_pipeline(
            alias_map=alias_map,
            crm_map=crm_map,
            ip_map=ip_map,
        )

        # Only low-confidence IP events (10.1.0.x) that have a domain but low confidence
        low_conf_ips = ["10.1.0.1", "10.1.0.2", "10.1.0.3", "10.1.0.4", "10.1.0.5"]
        for ip in low_conf_ips:
            signal = ResolutionInput(
                ip_address=ip,
                source_event_id=f"low-conf-test-{ip}",
                source_topic="harmoni.web.pageview",
            )
            enriched = await pipeline.process(signal, {"event_id": f"low-conf-test-{ip}"})
            # Must have been quarantined (quarantine_id set) OR confidence LOW/UNRESOLVABLE
            assert enriched.needs_quarantine or enriched.resolution.confidence in (
                ResolutionConfidence.LOW,
                ResolutionConfidence.UNRESOLVABLE,
            ), f"IP {ip} with confidence<0.70 was not quarantined"

        pending = await quarantine_repo.list_pending()
        assert len(pending) >= 5, "Expected at least 5 low-confidence entries in quarantine"

    @pytest.mark.asyncio
    async def test_unresolvable_events_quarantined(self) -> None:
        """Free-email events with no fallback must be quarantined."""
        pipeline, quarantine_repo = make_pipeline()
        free_emails = ["user@gmail.com", "contact@hotmail.com", "info@yahoo.com"]

        for email in free_emails:
            signal = ResolutionInput(
                email=email,
                source_event_id=f"free-{email}",
                source_topic="harmoni.email.engagement",
            )
            enriched = await pipeline.process(signal, {"event_id": f"free-{email}"})
            assert enriched.needs_quarantine is True
            assert enriched.quarantine_id is not None
            assert enriched.domain is None

        pending = await quarantine_repo.list_pending()
        assert len(pending) == 3


# ---------------------------------------------------------------------------
# Pipeline latency test (< 50ms p99 over 100 events)
# ---------------------------------------------------------------------------


class TestPipelineLatency:
    @pytest.mark.asyncio
    async def test_p99_latency_under_50ms(self) -> None:
        """Pipeline p99 latency must be < 50ms for DB-free (in-memory) path."""
        events, alias_map, crm_map, ip_map = make_synthetic_dataset()
        pipeline, _ = make_pipeline(alias_map=alias_map, crm_map=crm_map, ip_map=ip_map)

        latencies: list[float] = []
        # Use first 100 events (the dataset is exactly 100 samples)
        sample = events[:100]

        for synthetic in sample:
            raw_event = {"event_id": synthetic.signal.source_event_id}
            enriched = await pipeline.process(
                synthetic.signal,
                raw_event,
                upsert_member=False,
                enrich_new_accounts=False,
            )
            latencies.append(enriched.processing_ms)

        latencies.sort()
        p99_idx = int(len(latencies) * 0.99)
        p99_ms = latencies[min(p99_idx, len(latencies) - 1)]

        assert p99_ms < 50.0, (
            f"Pipeline p99 latency {p99_ms:.1f}ms exceeds 50ms target. "
            f"p50={statistics.median(latencies):.1f}ms"
        )


# ---------------------------------------------------------------------------
# Unit tests for EnrichedEvent
# ---------------------------------------------------------------------------


class TestEnrichedEvent:
    @pytest.mark.asyncio
    async def test_high_confidence_is_actionable(self) -> None:
        pipeline, _ = make_pipeline()
        signal = ResolutionInput(
            email="cfo@acme.com",
            source_event_id="unit-1",
            source_topic="harmoni.email.engagement",
        )
        enriched = await pipeline.process(signal, {"event_id": "unit-1"})
        assert enriched.is_actionable is True
        assert enriched.needs_quarantine is False
        assert enriched.domain == "acme.com"

    @pytest.mark.asyncio
    async def test_unresolvable_not_actionable(self) -> None:
        pipeline, _ = make_pipeline()
        signal = ResolutionInput(
            email="anon@gmail.com",
            source_event_id="unit-2",
            source_topic="harmoni.email.engagement",
        )
        enriched = await pipeline.process(signal, {"event_id": "unit-2"})
        assert enriched.is_actionable is False
        assert enriched.needs_quarantine is True

    @pytest.mark.asyncio
    async def test_member_upserted_for_business_email(self) -> None:
        pipeline, _ = make_pipeline()
        signal = ResolutionInput(
            email="vp-sales@acme.com",
            source_event_id="unit-3",
            source_topic="harmoni.crm.contact_activity",
            raw_context={"title": "VP of Sales", "first_name": "Alice", "last_name": "Smith"},
        )
        enriched = await pipeline.process(signal, {"event_id": "unit-3"}, upsert_member=True)
        assert enriched.member_id is not None

    @pytest.mark.asyncio
    async def test_no_member_upsert_for_free_email(self) -> None:
        pipeline, _ = make_pipeline()
        signal = ResolutionInput(
            email="user@gmail.com",
            source_event_id="unit-4",
            source_topic="harmoni.email.engagement",
        )
        enriched = await pipeline.process(signal, {"event_id": "unit-4"}, upsert_member=True)
        # Quarantined — no member_id
        assert enriched.member_id is None

    @pytest.mark.asyncio
    async def test_explicit_domain_always_high(self) -> None:
        pipeline, _ = make_pipeline()
        signal = ResolutionInput(
            explicit_domain="enterprise.com",
            source_event_id="unit-5",
            source_topic="harmoni.crm.contact_activity",
        )
        enriched = await pipeline.process(signal, {"event_id": "unit-5"})
        assert enriched.resolution.confidence == ResolutionConfidence.HIGH
        assert enriched.domain == "enterprise.com"
        assert enriched.quarantine_id is None

    @pytest.mark.asyncio
    async def test_processing_ms_is_positive(self) -> None:
        pipeline, _ = make_pipeline()
        signal = ResolutionInput(email="user@acme.com", source_event_id="unit-6", source_topic="t")
        enriched = await pipeline.process(signal, {"event_id": "unit-6"})
        assert enriched.processing_ms >= 0


# ---------------------------------------------------------------------------
# CRM xref strategy
# ---------------------------------------------------------------------------


class TestCRMStrategy:
    @pytest.mark.asyncio
    async def test_crm_resolves_when_email_is_free(self) -> None:
        crm_map = {("HUBSPOT", "hs-999"): "crm-resolved.com"}
        pipeline, _ = make_pipeline(crm_map=crm_map)
        signal = ResolutionInput(
            email="alice@gmail.com",  # free → falls through to CRM
            crm_company_id="hs-999",
            crm_source="HUBSPOT",
            source_event_id="crm-1",
            source_topic="harmoni.crm.contact_activity",
        )
        enriched = await pipeline.process(signal, {"event_id": "crm-1"})
        assert enriched.domain == "crm-resolved.com"
        assert enriched.resolution.confidence == ResolutionConfidence.MEDIUM
        assert enriched.resolution.strategy == "crm_xref"

    @pytest.mark.asyncio
    async def test_crm_miss_with_no_ip_quarantines(self) -> None:
        pipeline, quarantine_repo = make_pipeline()
        signal = ResolutionInput(
            email="user@gmail.com",
            crm_company_id="unknown-id",
            crm_source="HUBSPOT",
            source_event_id="crm-miss",
            source_topic="harmoni.crm.contact_activity",
        )
        enriched = await pipeline.process(signal, {"event_id": "crm-miss"})
        assert enriched.needs_quarantine is True
        pending = await quarantine_repo.list_pending()
        assert len(pending) == 1


# ---------------------------------------------------------------------------
# Alias strategy
# ---------------------------------------------------------------------------


class TestAliasStrategy:
    @pytest.mark.asyncio
    async def test_alias_email_resolves_to_canonical(self) -> None:
        alias_map = {"acquired-startup.io": "bigcorp.com"}
        pipeline, _ = make_pipeline(alias_map=alias_map)
        signal = ResolutionInput(
            email="ceo@acquired-startup.io",
            source_event_id="alias-1",
            source_topic="harmoni.email.engagement",
        )
        enriched = await pipeline.process(signal, {"event_id": "alias-1"})
        assert enriched.domain == "bigcorp.com"
        assert enriched.resolution.strategy == "alias_table"
        assert enriched.resolution.confidence == ResolutionConfidence.HIGH
