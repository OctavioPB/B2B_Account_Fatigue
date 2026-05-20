"""Tests for identity.quarantine — QuarantineQueue service layer."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from identity.models import QuarantineEntry
from identity.quarantine import QuarantineQueue
from identity.resolver import ResolutionConfidence, ResolutionResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_repo(
    enqueue_return: str = "qid-123",
    list_pending_return: list[QuarantineEntry] | None = None,
) -> MagicMock:
    repo = MagicMock()
    repo.enqueue = AsyncMock(return_value=enqueue_return)
    repo.list_pending = AsyncMock(return_value=list_pending_return or [])
    repo.resolve = AsyncMock()
    repo.discard = AsyncMock()
    return repo


def _make_entry(
    qid: str = "q1",
    status: str = "PENDING",
    confidence: str = "LOW",
) -> QuarantineEntry:
    return QuarantineEntry(
        id=qid,
        event_id="evt-1",
        source_topic="harmoni.web.pageview",
        raw_event={"event_id": "evt-1"},
        resolution_attempt={"strategy": "exhausted"},
        confidence=confidence,
        status=status,
    )


# ---------------------------------------------------------------------------
# QuarantineQueue.enqueue_result
# ---------------------------------------------------------------------------


class TestEnqueueResult:
    @pytest.mark.asyncio
    async def test_enqueue_returns_quarantine_id(self) -> None:
        repo = _make_repo(enqueue_return="qid-abc")
        queue = QuarantineQueue(repo)
        result = ResolutionResult(
            domain=None,
            account_id=None,
            confidence=ResolutionConfidence.UNRESOLVABLE,
            strategy="exhausted",
            reason="No strategy produced a resolvable domain",
        )
        qid = await queue.enqueue_result(
            result=result,
            source_topic="harmoni.web.pageview",
            raw_event={"event_id": "evt-1"},
        )
        assert qid == "qid-abc"

    @pytest.mark.asyncio
    async def test_enqueue_passes_correct_confidence(self) -> None:
        repo = _make_repo()
        queue = QuarantineQueue(repo)
        result = ResolutionResult(
            domain="maybe.com",
            account_id=None,
            confidence=ResolutionConfidence.LOW,
            strategy="ip_enrichment",
            reason="IP confidence=0.45",
        )
        await queue.enqueue_result(
            result=result,
            source_topic="harmoni.web.pageview",
            raw_event={"event_id": "evt-2"},
        )
        call_kwargs = repo.enqueue.call_args[1]
        assert call_kwargs["confidence"] == "LOW"

    @pytest.mark.asyncio
    async def test_enqueue_includes_strategy_in_resolution_attempt(self) -> None:
        repo = _make_repo()
        queue = QuarantineQueue(repo)
        result = ResolutionResult(
            domain=None,
            account_id=None,
            confidence=ResolutionConfidence.UNRESOLVABLE,
            strategy="email_domain",
            reason="Free email domain",
        )
        await queue.enqueue_result(
            result=result,
            source_topic="harmoni.email.engagement",
            raw_event={"event_id": "evt-3"},
        )
        call_kwargs = repo.enqueue.call_args[1]
        assert call_kwargs["resolution_attempt"]["strategy"] == "email_domain"
        assert call_kwargs["resolution_attempt"]["reason"] == "Free email domain"

    @pytest.mark.asyncio
    async def test_enqueue_extracts_event_id_from_raw_event(self) -> None:
        repo = _make_repo()
        queue = QuarantineQueue(repo)
        result = ResolutionResult(
            domain=None,
            account_id=None,
            confidence=ResolutionConfidence.UNRESOLVABLE,
            strategy="exhausted",
        )
        await queue.enqueue_result(
            result=result,
            source_topic="harmoni.crm.contact_activity",
            raw_event={"event_id": "custom-event-id-999"},
        )
        call_kwargs = repo.enqueue.call_args[1]
        assert call_kwargs["event_id"] == "custom-event-id-999"

    @pytest.mark.asyncio
    async def test_enqueue_handles_missing_event_id(self) -> None:
        repo = _make_repo()
        queue = QuarantineQueue(repo)
        result = ResolutionResult(
            domain=None,
            account_id=None,
            confidence=ResolutionConfidence.UNRESOLVABLE,
            strategy="exhausted",
        )
        # Should not raise even if event_id is absent
        await queue.enqueue_result(
            result=result,
            source_topic="harmoni.web.pageview",
            raw_event={},
        )
        repo.enqueue.assert_awaited_once()


# ---------------------------------------------------------------------------
# QuarantineQueue.list_pending
# ---------------------------------------------------------------------------


class TestListPending:
    @pytest.mark.asyncio
    async def test_returns_pending_entries(self) -> None:
        entries = [_make_entry("q1"), _make_entry("q2")]
        repo = _make_repo(list_pending_return=entries)
        queue = QuarantineQueue(repo)
        result = await queue.list_pending()
        assert len(result) == 2
        assert result[0].id == "q1"

    @pytest.mark.asyncio
    async def test_passes_limit_to_repo(self) -> None:
        repo = _make_repo()
        queue = QuarantineQueue(repo)
        await queue.list_pending(limit=50)
        repo.list_pending.assert_awaited_once_with(limit=50)

    @pytest.mark.asyncio
    async def test_default_limit_is_100(self) -> None:
        repo = _make_repo()
        queue = QuarantineQueue(repo)
        await queue.list_pending()
        repo.list_pending.assert_awaited_once_with(limit=100)


# ---------------------------------------------------------------------------
# QuarantineQueue.resolve
# ---------------------------------------------------------------------------


class TestResolve:
    @pytest.mark.asyncio
    async def test_resolve_delegates_to_repo(self) -> None:
        repo = _make_repo()
        queue = QuarantineQueue(repo)
        await queue.resolve(
            quarantine_id="qid-1",
            canonical_domain="acme.com",
            reviewer="ops@harmoni.io",
        )
        repo.resolve.assert_awaited_once_with(
            quarantine_id="qid-1",
            canonical_domain="acme.com",
            reviewer="ops@harmoni.io",
        )

    @pytest.mark.asyncio
    async def test_resolve_with_different_domains(self) -> None:
        repo = _make_repo()
        queue = QuarantineQueue(repo)
        await queue.resolve("qid-2", "newcorp.com", "reviewer@test.com")
        call_kwargs = repo.resolve.call_args[1]
        assert call_kwargs["canonical_domain"] == "newcorp.com"


# ---------------------------------------------------------------------------
# QuarantineQueue.discard
# ---------------------------------------------------------------------------


class TestDiscard:
    @pytest.mark.asyncio
    async def test_discard_delegates_to_repo(self) -> None:
        repo = _make_repo()
        queue = QuarantineQueue(repo)
        await queue.discard(quarantine_id="qid-5", reviewer="ops@harmoni.io")
        repo.discard.assert_awaited_once_with(
            quarantine_id="qid-5",
            reviewer="ops@harmoni.io",
        )
