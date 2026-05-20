"""NBA Orchestrator domain models for harmoni.

Defines the canonical NextBestAction output type, action taxonomy, dispatch
result, and conflict-resolution policy used by the NBAOrchestrator rules engine.

These types are account-first: every NBA carries account_id and account_domain.
Contact-level recommendations are not expressed here — see CLAUDE.md Hard Rule #2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Action taxonomy
# ---------------------------------------------------------------------------


class ActionType(str, Enum):
    """Seven canonical NBA action types. All production code uses these values.

    Order is significant: lower ordinal = higher urgency.
    """

    COOLDOWN         = "COOLDOWN"          # Pause all outreach (fatigue-driven)
    DEAL_REVIEW      = "DEAL_REVIEW"       # Human review required (churn critical)
    EXEC_ESCALATION  = "EXEC_ESCALATION"   # AE/VP engagement (churn high)
    PRICING_TRIGGER  = "PRICING_TRIGGER"   # Surface pricing/ROI content (intent high)
    ACCELERATE       = "ACCELERATE"        # Escalate cadence (all signals positive)
    RE_ENGAGE        = "RE_ENGAGE"         # Personalized re-engagement (drift)
    NURTURE          = "NURTURE"           # Low-pressure educational content (default)


# Priority map — lower number = higher urgency (used for conflict resolution)
ACTION_PRIORITY: dict[ActionType, int] = {
    ActionType.COOLDOWN:        1,
    ActionType.DEAL_REVIEW:     2,
    ActionType.EXEC_ESCALATION: 3,
    ActionType.PRICING_TRIGGER: 4,
    ActionType.ACCELERATE:      5,
    ActionType.RE_ENGAGE:       6,
    ActionType.NURTURE:         7,
}

# How long each NBA recommendation is valid before it must be refreshed
ACTION_EXPIRY_HOURS: dict[ActionType, int] = {
    ActionType.COOLDOWN:        168,   # 7 days — matches fatigue cooldown window
    ActionType.DEAL_REVIEW:     168,   # 7 days — human review window
    ActionType.EXEC_ESCALATION:  48,
    ActionType.PRICING_TRIGGER:  72,
    ActionType.ACCELERATE:       24,
    ActionType.RE_ENGAGE:        72,
    ActionType.NURTURE:          24,
}

# Actions that are "protected": never overwritten by lower-priority recommendations
PROTECTED_ACTION_TYPES: frozenset[ActionType] = frozenset({
    ActionType.COOLDOWN,
    ActionType.DEAL_REVIEW,
})


# ---------------------------------------------------------------------------
# NextBestAction
# ---------------------------------------------------------------------------


@dataclass
class NextBestAction:
    """System-recommended marketing or sales action for a target account.

    Produced by NBAOrchestrator. Exactly one NBA is active per account
    at any point in time. The conflict-resolution policy prevents lower-priority
    actions from overwriting protected COOLDOWN / DEAL_REVIEW recommendations.
    """

    account_id: str
    account_domain: str
    action_type: ActionType
    rationale: str
    triggered_by: list[str] = field(default_factory=list)

    # Score snapshots for audit and model evaluation
    fatigue_score: float | None = None
    intent_score: float | None = None
    churn_probability: float | None = None

    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    is_active: bool = True

    @property
    def priority(self) -> int:
        return ACTION_PRIORITY[self.action_type]

    @property
    def expires_at(self) -> datetime:
        hours = ACTION_EXPIRY_HOURS[self.action_type]
        return self.created_at + timedelta(hours=hours)

    @property
    def is_protected(self) -> bool:
        """True for COOLDOWN and DEAL_REVIEW — not overwritten by lower-priority NBAs."""
        return self.action_type in PROTECTED_ACTION_TYPES

    def to_dict(self) -> dict[str, Any]:
        return {
            "account_id":        self.account_id,
            "account_domain":    self.account_domain,
            "action_type":       self.action_type.value,
            "priority":          self.priority,
            "rationale":         self.rationale,
            "triggered_by":      self.triggered_by,
            "fatigue_score":     self.fatigue_score,
            "intent_score":      self.intent_score,
            "churn_probability": self.churn_probability,
            "expires_at":        self.expires_at.isoformat(),
            "created_at":        self.created_at.isoformat(),
            "is_active":         self.is_active,
        }


# ---------------------------------------------------------------------------
# Dispatch result
# ---------------------------------------------------------------------------


@dataclass
class DispatchResult:
    """Outcome of dispatching one NextBestAction to an external platform."""

    success: bool
    platform: str           # e.g. "hubspot", "salesloft", "slack"
    action_id: str          # local NextBestAction identifier
    external_id: str | None = None   # ID in the external system (if created)
    message: str = ""


# ---------------------------------------------------------------------------
# Conflict resolution helpers
# ---------------------------------------------------------------------------


def should_overwrite(existing: NextBestAction, incoming: NextBestAction) -> bool:
    """Return True if the incoming NBA should replace the existing active NBA.

    Policy:
    - Protected actions (COOLDOWN, DEAL_REVIEW) are never overwritten by
      lower-priority actions — they persist until they expire or are manually cleared.
    - All other existing actions are replaced by any incoming action.

    Args:
        existing: The currently active NBA for the account.
        incoming: The newly computed NBA recommendation.
    """
    if not existing.is_active:
        return True
    if existing.is_protected:
        # A protected action can only be overwritten by an equally or more urgent action
        return incoming.priority <= existing.priority
    return True
