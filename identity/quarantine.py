"""Quarantine queue service for unresolvable and low-confidence signals.

QuarantineQueue wraps QuarantineRepository to provide a service-layer
interface used by ResolutionPipeline. It handles:

- Enqueuing LOW/UNRESOLVABLE resolution results (never silently drop)
- Listing pending items for the ops review UI
- Resolving or discarding quarantined entries

Per ADR 0005: every unresolved event must be inspectable and recoverable.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from identity.repository import QuarantineRepository

from identity.models import QuarantineEntry
from identity.resolver import ResolutionResult

logger = logging.getLogger(__name__)


class QuarantineQueue:
    """Service layer over QuarantineRepository.

    Args:
        repo: Injected repository — swap for in-memory stub in tests.
    """

    def __init__(self, repo: "QuarantineRepository") -> None:
        self._repo = repo

    async def enqueue_result(
        self,
        result: ResolutionResult,
        source_topic: str,
        raw_event: dict[str, Any],
    ) -> str:
        """Enqueue a resolution result that needs manual review.

        Builds the ``resolution_attempt`` JSON from the result and writes
        to the quarantine table. Returns the quarantine entry UUID.

        Args:
            result:      The (LOW or UNRESOLVABLE) ResolutionResult.
            source_topic: Kafka topic the originating event came from.
            raw_event:   Original raw event payload.

        Returns:
            UUID string of the created quarantine entry.
        """
        event_id = raw_event.get("event_id", "")
        resolution_attempt: dict[str, Any] = {
            "strategy": result.strategy,
            "confidence": result.confidence.value,
            "domain": result.domain,
            "reason": result.reason,
        }
        qid = await self._repo.enqueue(
            event_id=str(event_id),
            source_topic=source_topic,
            raw_event=raw_event,
            resolution_attempt=resolution_attempt,
            confidence=result.confidence.value,
        )
        logger.info(
            "Quarantined event_id=%s confidence=%s strategy=%s qid=%s",
            event_id,
            result.confidence.value,
            result.strategy,
            qid,
        )
        return qid

    async def list_pending(self, limit: int = 100) -> list[QuarantineEntry]:
        """Return up to ``limit`` PENDING quarantine entries, oldest first."""
        return await self._repo.list_pending(limit=limit)

    async def resolve(
        self,
        quarantine_id: str,
        canonical_domain: str,
        reviewer: str,
    ) -> None:
        """Mark a quarantine entry RESOLVED with the correct canonical domain.

        Args:
            quarantine_id:   UUID of the quarantine entry.
            canonical_domain: The correct account domain determined by ops review.
            reviewer:         Identity of the reviewer (email or username).
        """
        await self._repo.resolve(
            quarantine_id=quarantine_id,
            canonical_domain=canonical_domain,
            reviewer=reviewer,
        )
        logger.info(
            "Quarantine entry %s resolved → domain=%s by reviewer=%s",
            quarantine_id,
            canonical_domain,
            reviewer,
        )

    async def discard(self, quarantine_id: str, reviewer: str) -> None:
        """Mark a quarantine entry DISCARDED (cannot be recovered, kept for audit).

        Args:
            quarantine_id: UUID of the quarantine entry.
            reviewer:      Identity of the reviewer.
        """
        await self._repo.discard(quarantine_id=quarantine_id, reviewer=reviewer)
        logger.info(
            "Quarantine entry %s discarded by reviewer=%s",
            quarantine_id,
            reviewer,
        )
