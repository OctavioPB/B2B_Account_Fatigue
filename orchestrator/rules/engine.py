"""NBAOrchestrator — deterministic rules-based Next Best Action engine.

Decision tree mapping (FatigueScore × IntentScore × ChurnProbability) → NextBestAction.

Rule priority (first match wins):

  1. COOLDOWN        — fatigue HIGH or CRITICAL
     → All outreach paused. Fatigue override supersedes all other signals.

  2. DEAL_REVIEW     — churn CRITICAL
     → Deal is imminently at risk. Immediate human review required regardless
       of intent level.

  3. EXEC_ESCALATION — churn HIGH
     → Deal drifting toward loss. Route to AE or VP for executive engagement.

  4. ACCELERATE      — intent ≥ 70 AND fatigue LOW AND churn LOW
     → All conditions optimal. Push cadence and volume.

  5. PRICING_TRIGGER — intent ≥ 70 AND fatigue LOW/MEDIUM AND churn LOW/MEDIUM
     → Buying committee is interested. Surface pricing/ROI content.

  6. RE_ENGAGE       — churn MEDIUM AND intent < 70
     → Account drifting. Personalized re-engagement before it deteriorates further.

  7. NURTURE         — default fallback
     → Low-pressure educational content; maintain relationship without pressure.

FEATURE_RL_ORCHESTRATOR guard: the RL policy module is never invoked by this
engine. Any attempt to enable it requires the env var to be explicitly set to
"true" and will fail in production CI where the var is absent.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from orchestrator.models import (
    ACTION_PRIORITY,
    ActionType,
    NextBestAction,
    should_overwrite,
)
from scoring.models import (
    AccountFatigueScore,
    ChurnPrediction,
    ChurnRiskLevel,
    FatigueSeverity,
    IntentScore,
)

logger = logging.getLogger(__name__)

# Minimum intent score considered "high intent" for PRICING_TRIGGER / ACCELERATE
_HIGH_INTENT_THRESHOLD = 70.0


class NBAOrchestrator:
    """Deterministic rules-based NBA orchestrator.

    Production code MUST use this class. The RL policy (orchestrator/rl/) is
    isolated behind the FEATURE_RL_ORCHESTRATOR=true flag and is never active
    in CI or production environments.

    Usage::

        orchestrator = NBAOrchestrator()
        action = orchestrator.decide(account_id, domain, fatigue, intent, churn)
    """

    def __init__(self) -> None:
        _assert_rl_flag_is_off()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def decide(
        self,
        account_id: str,
        account_domain: str,
        fatigue: AccountFatigueScore,
        intent: IntentScore,
        churn: ChurnPrediction,
        as_of: datetime | None = None,
    ) -> NextBestAction:
        """Apply the decision tree and return a NextBestAction for one account.

        Args:
            account_id:      Account UUID string.
            account_domain:  Normalised company domain.
            fatigue:         Latest AccountFatigueScore for the account.
            intent:          Latest IntentScore for the account.
            churn:           Latest ChurnPrediction for the account.
            as_of:           Timestamp for the created_at field (defaults to UTC now).

        Returns:
            NextBestAction (not yet persisted).
        """
        as_of = as_of or datetime.now(timezone.utc)
        action_type, rationale, triggered_by = _apply_rules(fatigue, intent, churn)

        action = NextBestAction(
            account_id=account_id,
            account_domain=account_domain,
            action_type=action_type,
            rationale=rationale,
            triggered_by=triggered_by,
            fatigue_score=round(fatigue.score, 2),
            intent_score=round(intent.score, 2),
            churn_probability=round(churn.churn_probability, 4),
            created_at=as_of,
        )

        logger.debug(
            "NBA decided account=%s action=%s priority=%d",
            account_domain, action_type.value, action.priority,
        )
        return action

    def resolve(
        self,
        existing: NextBestAction | None,
        incoming: NextBestAction,
    ) -> NextBestAction:
        """Apply conflict resolution: return the action that should be active.

        If existing is None or the incoming action should overwrite it, returns
        incoming (with existing deactivated by the caller).

        If the existing protected action blocks the incoming one, returns existing
        unchanged so the caller knows not to create a new row.
        """
        if existing is None or should_overwrite(existing, incoming):
            return incoming
        logger.debug(
            "Conflict resolution: keeping existing %s over incoming %s for account=%s",
            existing.action_type.value, incoming.action_type.value, incoming.account_domain,
        )
        return existing


# ---------------------------------------------------------------------------
# Decision tree (module-level pure function — easy to unit-test directly)
# ---------------------------------------------------------------------------


def _apply_rules(
    fatigue: AccountFatigueScore,
    intent: IntentScore,
    churn: ChurnPrediction,
) -> tuple[ActionType, str, list[str]]:
    """Return (action_type, rationale, triggered_by) for the given signal state."""

    sev   = fatigue.severity
    iscore = intent.score
    clevel = churn.risk_level
    cprob  = churn.churn_probability

    # Rule 1: Fatigue override — all outreach paused
    if sev in (FatigueSeverity.HIGH, FatigueSeverity.CRITICAL):
        return (
            ActionType.COOLDOWN,
            f"Account fatigue is {sev.value} (score {fatigue.score:.1f}) — "
            "all outreach paused to prevent permanent opt-out.",
            [f"fatigue_severity={sev.value}", f"fatigue_score={fatigue.score:.1f}"],
        )

    # Rule 2: Churn critical — immediate human review
    if clevel == ChurnRiskLevel.CRITICAL:
        return (
            ActionType.DEAL_REVIEW,
            f"Churn probability is CRITICAL ({cprob:.0%}) — "
            "deal requires immediate human review before any automated outreach.",
            [f"churn_risk_level=CRITICAL", f"churn_probability={cprob:.3f}"],
        )

    # Rule 3: Churn high — executive escalation
    if clevel == ChurnRiskLevel.HIGH:
        return (
            ActionType.EXEC_ESCALATION,
            f"Churn probability is HIGH ({cprob:.0%}) — "
            "route to AE or VP for executive-to-executive engagement.",
            [f"churn_risk_level=HIGH", f"churn_probability={cprob:.3f}"],
        )

    # Rule 4: All signals positive — accelerate cadence
    if (iscore >= _HIGH_INTENT_THRESHOLD
            and sev == FatigueSeverity.LOW
            and clevel == ChurnRiskLevel.LOW):
        return (
            ActionType.ACCELERATE,
            f"Intent is high ({iscore:.1f}), fatigue is LOW, churn is LOW — "
            "all signals positive; escalate outreach cadence.",
            [
                f"intent_score={iscore:.1f}",
                f"fatigue_severity=LOW",
                f"churn_risk_level=LOW",
            ],
        )

    # Rule 5: High intent with some friction — surface pricing content
    if (iscore >= _HIGH_INTENT_THRESHOLD
            and sev in (FatigueSeverity.LOW, FatigueSeverity.MEDIUM)
            and clevel in (ChurnRiskLevel.LOW, ChurnRiskLevel.MEDIUM)):
        return (
            ActionType.PRICING_TRIGGER,
            f"Intent is high ({iscore:.1f}) with manageable fatigue ({sev.value}) — "
            "surface pricing and ROI content to advance the commercial conversation.",
            [
                f"intent_score={iscore:.1f}",
                f"fatigue_severity={sev.value}",
                f"churn_risk_level={clevel.value}",
            ],
        )

    # Rule 6: Account drifting — personalised re-engagement
    if clevel == ChurnRiskLevel.MEDIUM:
        return (
            ActionType.RE_ENGAGE,
            f"Churn probability is MEDIUM ({cprob:.0%}) and intent is below threshold "
            f"({iscore:.1f}) — personalised re-engagement sequence required.",
            [
                f"churn_risk_level=MEDIUM",
                f"churn_probability={cprob:.3f}",
                f"intent_score={iscore:.1f}",
            ],
        )

    # Rule 7: Default — nurture
    return (
        ActionType.NURTURE,
        f"No urgent signal detected (fatigue={sev.value}, intent={iscore:.1f}, "
        f"churn={clevel.value}) — maintain relationship with low-pressure educational content.",
        [
            f"fatigue_severity={sev.value}",
            f"intent_score={iscore:.1f}",
            f"churn_risk_level={clevel.value}",
        ],
    )


# ---------------------------------------------------------------------------
# Feature flag guard
# ---------------------------------------------------------------------------


def _assert_rl_flag_is_off() -> None:
    """Raise RuntimeError if FEATURE_RL_ORCHESTRATOR is enabled.

    This guard runs at NBAOrchestrator instantiation time. Production code that
    instantiates NBAOrchestrator will fail fast if the flag is accidentally enabled
    without the RL policy having passed offline evaluation benchmarks.
    """
    flag = os.getenv("FEATURE_RL_ORCHESTRATOR", "false").strip().lower()
    if flag == "true":
        raise RuntimeError(
            "FEATURE_RL_ORCHESTRATOR=true is set but the RL policy has not passed "
            "offline evaluation benchmarks. NBAOrchestrator (rules engine) cannot "
            "be used alongside the RL flag. Either disable the flag or use the RL "
            "policy class directly via orchestrator.rl — see CLAUDE.md Hard Rule #4."
        )
