"""ActionDispatcher — abstract interface and stub implementations.

The dispatcher is the boundary between the NBA orchestrator (which decides
what to do) and external platforms (which execute it). Each platform has a
concrete stub that logs the action as-if dispatched, allowing the system to
operate fully in development and test environments without live API keys.

Abstract interface:
    ActionDispatcher.dispatch(action)  → DispatchResult
    ActionDispatcher.cancel(action_id) → bool

Stub implementations (all log but do not make real API calls):
    HubSpotDispatcher    — creates a HubSpot Task on the account's company record
    SalesloftDispatcher  — adds account to a Salesloft Cadence
    SlackDispatcher      — posts a NBA alert to a configured Slack channel

Production note: replace stubs with real HTTP clients when API credentials
are available. Keep the same ActionDispatcher interface — the DAG calls only
the abstract methods.
"""

from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from typing import Any

from orchestrator.models import ActionType, DispatchResult, NextBestAction

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class ActionDispatcher(ABC):
    """Abstract interface for dispatching NextBestActions to external platforms."""

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Human-readable platform identifier (e.g. 'hubspot', 'salesloft')."""

    @abstractmethod
    def dispatch(self, action: NextBestAction) -> DispatchResult:
        """Send the action to the external platform.

        Args:
            action: The NextBestAction to dispatch.

        Returns:
            DispatchResult indicating success/failure and any external ID.
        """

    @abstractmethod
    def cancel(self, action_id: str) -> bool:
        """Cancel or close a previously dispatched action in the external platform.

        Args:
            action_id: Local NextBestAction identifier (UUID string).

        Returns:
            True if cancelled successfully; False if not found or not cancellable.
        """


# ---------------------------------------------------------------------------
# Stub: HubSpot
# ---------------------------------------------------------------------------


class HubSpotDispatcher(ActionDispatcher):
    """Stub dispatcher that simulates creating HubSpot Tasks.

    In production, replace the _call_hubspot_api() body with a real call
    to the HubSpot CRM v3 Tasks API using the HUBSPOT_API_KEY env var.
    """

    _ACTION_TO_TASK_TYPE: dict[ActionType, str] = {
        ActionType.COOLDOWN:        "TODO",
        ActionType.DEAL_REVIEW:     "TODO",
        ActionType.EXEC_ESCALATION: "CALL",
        ActionType.PRICING_TRIGGER: "EMAIL",
        ActionType.ACCELERATE:      "EMAIL",
        ActionType.RE_ENGAGE:       "EMAIL",
        ActionType.NURTURE:         "EMAIL",
    }

    @property
    def platform_name(self) -> str:
        return "hubspot"

    def dispatch(self, action: NextBestAction) -> DispatchResult:
        task_type  = self._ACTION_TO_TASK_TYPE.get(action.action_type, "TODO")
        fake_task_id = f"hs-task-{uuid.uuid4().hex[:8]}"

        logger.info(
            "[STUB:HubSpot] CREATE Task type=%s account=%s action=%s rationale='%s' "
            "→ fake_id=%s",
            task_type, action.account_domain, action.action_type.value,
            action.rationale[:80], fake_task_id,
        )
        return DispatchResult(
            success=True,
            platform=self.platform_name,
            action_id=action.account_id,
            external_id=fake_task_id,
            message=f"HubSpot Task {task_type} created (stub)",
        )

    def cancel(self, action_id: str) -> bool:
        logger.info("[STUB:HubSpot] CANCEL action_id=%s", action_id)
        return True


# ---------------------------------------------------------------------------
# Stub: Salesloft
# ---------------------------------------------------------------------------


class SalesloftDispatcher(ActionDispatcher):
    """Stub dispatcher that simulates adding accounts to Salesloft Cadences.

    In production, replace the stub bodies with calls to the Salesloft v2 API
    using the SALESLOFT_API_KEY env var. Each action type maps to a named cadence.
    """

    _ACTION_TO_CADENCE: dict[ActionType, str] = {
        ActionType.COOLDOWN:        None,                    # Never cadence a cooling-down account
        ActionType.DEAL_REVIEW:     "deal-review-internal",
        ActionType.EXEC_ESCALATION: "exec-escalation-ae",
        ActionType.PRICING_TRIGGER: "pricing-roi-sequence",
        ActionType.ACCELERATE:      "high-velocity-sequence",
        ActionType.RE_ENGAGE:       "re-engagement-7day",
        ActionType.NURTURE:         "nurture-monthly",
    }

    @property
    def platform_name(self) -> str:
        return "salesloft"

    def dispatch(self, action: NextBestAction) -> DispatchResult:
        cadence = self._ACTION_TO_CADENCE.get(action.action_type)

        if cadence is None:
            logger.info(
                "[STUB:Salesloft] SKIP account=%s action=%s — no cadence for COOLDOWN",
                action.account_domain, action.action_type.value,
            )
            return DispatchResult(
                success=True,
                platform=self.platform_name,
                action_id=action.account_id,
                external_id=None,
                message="Salesloft: skipped — COOLDOWN accounts are not cadenced",
            )

        fake_enrollment_id = f"sl-enroll-{uuid.uuid4().hex[:8]}"
        logger.info(
            "[STUB:Salesloft] ENROLL account=%s cadence=%s action=%s → fake_id=%s",
            action.account_domain, cadence, action.action_type.value, fake_enrollment_id,
        )
        return DispatchResult(
            success=True,
            platform=self.platform_name,
            action_id=action.account_id,
            external_id=fake_enrollment_id,
            message=f"Enrolled in Salesloft cadence '{cadence}' (stub)",
        )

    def cancel(self, action_id: str) -> bool:
        logger.info("[STUB:Salesloft] REMOVE_FROM_CADENCE action_id=%s", action_id)
        return True


# ---------------------------------------------------------------------------
# Stub: Slack
# ---------------------------------------------------------------------------


_SLACK_EMOJI: dict[ActionType, str] = {
    ActionType.COOLDOWN:        ":no_entry:",
    ActionType.DEAL_REVIEW:     ":rotating_light:",
    ActionType.EXEC_ESCALATION: ":telephone_receiver:",
    ActionType.PRICING_TRIGGER: ":moneybag:",
    ActionType.ACCELERATE:      ":rocket:",
    ActionType.RE_ENGAGE:       ":wave:",
    ActionType.NURTURE:         ":seedling:",
}


class SlackDispatcher(ActionDispatcher):
    """Stub dispatcher that simulates posting NBA alerts to a Slack channel.

    In production, replace the stub body with a real Slack Web API call using
    the SLACK_BOT_TOKEN env var and a SLACK_NBA_CHANNEL_ID env var.
    """

    @property
    def platform_name(self) -> str:
        return "slack"

    def dispatch(self, action: NextBestAction) -> DispatchResult:
        emoji = _SLACK_EMOJI.get(action.action_type, ":bell:")
        fake_ts = f"17{uuid.uuid4().int % 10**11}.{uuid.uuid4().int % 10**6:06d}"

        message = (
            f"{emoji} *{action.action_type.value}* — `{action.account_domain}` "
            f"| intent={action.intent_score:.1f} "
            f"churn={action.churn_probability:.0%} "
            f"fatigue={action.fatigue_score:.1f}"
        )

        logger.info(
            "[STUB:Slack] POST channel=#nba-alerts message='%s' → ts=%s",
            message, fake_ts,
        )
        return DispatchResult(
            success=True,
            platform=self.platform_name,
            action_id=action.account_id,
            external_id=fake_ts,
            message="Slack message posted to #nba-alerts (stub)",
        )

    def cancel(self, action_id: str) -> bool:
        # Slack messages are not cancelled — they're informational
        logger.info("[STUB:Slack] NOOP cancel action_id=%s (Slack messages not cancelled)", action_id)
        return False


# ---------------------------------------------------------------------------
# Composite dispatcher — fans out to all registered platforms
# ---------------------------------------------------------------------------


class CompositeDispatcher:
    """Dispatch one action to multiple platforms in sequence.

    If one platform fails, the others still receive the action. Results are
    aggregated and returned as a list.

    Usage::

        dispatcher = CompositeDispatcher([
            HubSpotDispatcher(),
            SalesloftDispatcher(),
            SlackDispatcher(),
        ])
        results = dispatcher.dispatch_all(action)
    """

    def __init__(self, dispatchers: list[ActionDispatcher]) -> None:
        self._dispatchers = dispatchers

    def dispatch_all(self, action: NextBestAction) -> list[DispatchResult]:
        results = []
        for d in self._dispatchers:
            try:
                result = d.dispatch(action)
                results.append(result)
            except Exception:
                logger.error(
                    "Dispatcher %s failed for account=%s action=%s",
                    d.platform_name, action.account_domain, action.action_type.value,
                    exc_info=True,
                )
                results.append(DispatchResult(
                    success=False,
                    platform=d.platform_name,
                    action_id=action.account_id,
                    message="Dispatch failed — see logs for details",
                ))
        return results

    def cancel_all(self, action_id: str) -> dict[str, bool]:
        return {d.platform_name: d.cancel(action_id) for d in self._dispatchers}
