"""Identity resolution pipeline — the main orchestration entry point.

ResolutionPipeline.process() ties together:
1. AsyncAccountResolver   — resolve signal → Account domain + confidence
2. BaseEnricher           — firmographic enrichment (if account is new)
3. CommitteeMemberRepository — upsert the contact as a CommitteeMember
4. QuarantineQueue        — route LOW/UNRESOLVABLE signals to quarantine

EnrichedEvent is the output type returned to the caller (e.g. a Kafka
consumer handler) after processing.

Callers must check EnrichedEvent.needs_quarantine to know whether to
forward the event downstream or surface it in the ops review queue.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from identity.enrichment.base import BaseEnricher, BaseIPEnricher
    from identity.repository import AccountRepository, CommitteeMemberRepository
    from identity.quarantine import QuarantineQueue

from identity.models import ResolutionInput
from identity.resolver import AsyncAccountResolver, ResolutionConfidence, ResolutionResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pipeline output
# ---------------------------------------------------------------------------


@dataclass
class EnrichedEvent:
    """Result of processing a raw signal through the identity pipeline.

    Attributes:
        resolution:      Domain + account_id + confidence tier.
        account_id:      Convenience alias for resolution.account_id.
        domain:          Convenience alias for resolution.domain.
        member_id:       CommitteeMember UUID if contact was upserted; None otherwise.
        quarantine_id:   Quarantine entry UUID if routed to quarantine; None otherwise.
        processing_ms:   Wall-clock milliseconds for the full pipeline run.
        raw_event:       Original raw event dict passed in by the caller.
    """

    resolution: ResolutionResult
    account_id: str | None
    domain: str | None
    member_id: str | None = None
    quarantine_id: str | None = None
    processing_ms: float = 0.0
    raw_event: dict[str, Any] = field(default_factory=dict)

    @property
    def is_actionable(self) -> bool:
        return self.resolution.is_actionable()

    @property
    def needs_quarantine(self) -> bool:
        return self.resolution.needs_quarantine()


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


class ResolutionPipeline:
    """End-to-end identity resolution and enrichment pipeline.

    Args:
        resolver:         AsyncAccountResolver (multi-strategy, DB-backed).
        account_repo:     AccountRepository (to trigger firmographic enrichment).
        member_repo:      CommitteeMemberRepository (to upsert committee members).
        quarantine:       QuarantineQueue (to route unresolvable signals).
        firmographic:     Optional BaseEnricher to fetch firmographic data.
    """

    def __init__(
        self,
        resolver: AsyncAccountResolver,
        account_repo: "AccountRepository",
        member_repo: "CommitteeMemberRepository",
        quarantine: "QuarantineQueue",
        firmographic: "BaseEnricher | None" = None,
    ) -> None:
        self._resolver = resolver
        self._account_repo = account_repo
        self._member_repo = member_repo
        self._quarantine = quarantine
        self._firmographic = firmographic

    async def process(
        self,
        signal: ResolutionInput,
        raw_event: dict[str, Any],
        *,
        upsert_member: bool = True,
        enrich_new_accounts: bool = True,
    ) -> EnrichedEvent:
        """Process a raw signal through the full identity pipeline.

        Args:
            signal:              All available resolution inputs.
            raw_event:           Original event payload (stored in quarantine if needed).
            upsert_member:       If True, upsert the contact as a CommitteeMember.
            enrich_new_accounts: If True, fire firmographic enrichment for new accounts.

        Returns:
            EnrichedEvent with resolution result and any side-effect IDs.
        """
        t0 = time.monotonic()

        # ------------------------------------------------------------------
        # Step 1: Resolve signal → Account
        # ------------------------------------------------------------------
        resolution = await self._resolver.resolve(signal)
        account_id = resolution.account_id
        domain = resolution.domain

        # ------------------------------------------------------------------
        # Step 2: Route LOW/UNRESOLVABLE to quarantine
        # ------------------------------------------------------------------
        quarantine_id: str | None = None
        if resolution.needs_quarantine():
            try:
                quarantine_id = await self._quarantine.enqueue_result(
                    result=resolution,
                    source_topic=signal.source_topic,
                    raw_event=raw_event,
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "CRITICAL: quarantine enqueue failed for event_id=%s: %s",
                    signal.source_event_id,
                    exc,
                )
            elapsed = (time.monotonic() - t0) * 1000
            return EnrichedEvent(
                resolution=resolution,
                account_id=account_id,
                domain=domain,
                quarantine_id=quarantine_id,
                processing_ms=elapsed,
                raw_event=raw_event,
            )

        # ------------------------------------------------------------------
        # Step 3: Firmographic enrichment for newly created accounts
        # ------------------------------------------------------------------
        if enrich_new_accounts and domain and self._firmographic:
            account = await self._account_repo.get_by_domain(domain)
            if account is not None and account.firmographic_enriched_at is None:
                await self._enrich_firmographic(domain)

        # ------------------------------------------------------------------
        # Step 4: Upsert CommitteeMember if email is available
        # ------------------------------------------------------------------
        member_id: str | None = None
        if upsert_member and signal.email and account_id:
            member_id = await self._upsert_member(signal, account_id)

        elapsed = (time.monotonic() - t0) * 1000
        logger.debug(
            "ResolutionPipeline: domain=%s confidence=%s strategy=%s member_id=%s %.1fms",
            domain,
            resolution.confidence.value,
            resolution.strategy,
            member_id,
            elapsed,
        )

        return EnrichedEvent(
            resolution=resolution,
            account_id=account_id,
            domain=domain,
            member_id=member_id,
            processing_ms=elapsed,
            raw_event=raw_event,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _enrich_firmographic(self, domain: str) -> None:
        """Fire firmographic enrichment and persist the result."""
        assert self._firmographic is not None
        try:
            firm_data = await self._firmographic.enrich(domain)
            if firm_data is not None:
                await self._account_repo.update_firmographic(domain, firm_data)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Firmographic enrichment failed for %s: %s", domain, exc)

    async def _upsert_member(self, signal: ResolutionInput, account_id: str) -> str | None:
        """Upsert CommitteeMember for the contact in the signal."""
        email = signal.email
        if not email:
            return None
        # Extract contact attributes from raw context if provided by connector
        ctx = signal.raw_context or {}
        try:
            member = await self._member_repo.upsert_member(
                account_id=account_id,
                email=email,
                title=ctx.get("title") or ctx.get("job_title"),
                first_name=ctx.get("first_name"),
                last_name=ctx.get("last_name"),
                crm_contact_id=signal.crm_contact_id,
                crm_source=signal.crm_source,
            )
            await self._member_repo.touch_last_signal(member.id)
            return member.id
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "CommitteeMember upsert failed for email=%s account=%s: %s",
                email, account_id, exc,
            )
            return None
