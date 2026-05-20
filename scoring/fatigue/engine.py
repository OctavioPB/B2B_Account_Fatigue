"""FatigueScoreEngine — composite Account Fatigue Score computation.

Combines five component calculators into a single weighted score (0–100).
Component weights are configurable per account segment to reflect different
buying committee dynamics across market segments.

Default weights (sum to 1.0):

    outreach_frequency    0.30  — volume is the primary fatigue driver
    negative_signal       0.30  — opt-outs / spam are the sharpest signal
    engagement_decay      0.25  — falling rates indicate passive resistance
    contact_concentration 0.10  — over-reliance on one member
    recency               0.05  — staleness of last meaningful exchange

Severity thresholds:

    LOW      0  – 30   normal operation, monitor only
    MEDIUM  30  – 60   consider reducing cadence
    HIGH    60  – 80   trigger cooldown; NBA → NURTURE or RE_ENGAGE
    CRITICAL 80 – 100  hard cooldown; NBA → EXEC_ESCALATION or DEAL_REVIEW
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from scoring.fatigue.components import (
    ComponentResult,
    ContactConcentrationCalculator,
    EngagementDecayCalculator,
    NegativeSignalCalculator,
    OutreachFrequencyCalculator,
    RecencyCalculator,
)
from scoring.models import (
    AccountFatigueScore,
    FatigueComponent,
    FatigueSeverity,
    OutreachDaySummary,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Severity classification
# ---------------------------------------------------------------------------

# Thresholds are lower bounds for each tier (score >= threshold → tier)
_SEVERITY_THRESHOLDS: list[tuple[float, FatigueSeverity]] = [
    (80.0, FatigueSeverity.CRITICAL),
    (60.0, FatigueSeverity.HIGH),
    (30.0, FatigueSeverity.MEDIUM),
    (0.0,  FatigueSeverity.LOW),
]


def _classify_severity(score: float) -> FatigueSeverity:
    for threshold, severity in _SEVERITY_THRESHOLDS:
        if score >= threshold:
            return severity
    return FatigueSeverity.LOW


# ---------------------------------------------------------------------------
# Default and segment-specific component weights
# ---------------------------------------------------------------------------

_DEFAULT_WEIGHTS: dict[str, float] = {
    "outreach_frequency":     0.30,
    "negative_signal":        0.30,
    "engagement_decay":       0.25,
    "contact_concentration":  0.10,
    "recency":                0.05,
}

# Enterprise: negative signals and engagement matter most (lower volume tolerance)
# SMB: frequency is a stronger fatigue signal (higher volume expected but tires faster)
_SEGMENT_WEIGHTS: dict[str, dict[str, float]] = {
    "ENTERPRISE": {
        "outreach_frequency":     0.20,
        "negative_signal":        0.35,
        "engagement_decay":       0.30,
        "contact_concentration":  0.10,
        "recency":                0.05,
    },
    "MID_MARKET": {
        "outreach_frequency":     0.30,
        "negative_signal":        0.30,
        "engagement_decay":       0.25,
        "contact_concentration":  0.10,
        "recency":                0.05,
    },
    "SMB": {
        "outreach_frequency":     0.35,
        "negative_signal":        0.28,
        "engagement_decay":       0.22,
        "contact_concentration":  0.10,
        "recency":                0.05,
    },
}


def _resolve_weights(account_segment: str) -> dict[str, float]:
    return _SEGMENT_WEIGHTS.get(account_segment, _DEFAULT_WEIGHTS)


# ---------------------------------------------------------------------------
# FatigueScoreEngine
# ---------------------------------------------------------------------------


class FatigueScoreEngine:
    """Compute a composite AccountFatigueScore for a single account.

    Usage::

        engine = FatigueScoreEngine()
        score = engine.compute(
            account_id="uuid",
            account_domain="acme.com",
            outreach_rows=rows,
            account_segment="ENTERPRISE",
        )

    Args:
        weights_override: If provided, replaces all segment-based weight
            selection. Useful for A/B testing weight configurations.
    """

    def __init__(
        self,
        weights_override: dict[str, float] | None = None,
    ) -> None:
        self._weights_override = weights_override
        self._freq_calc   = OutreachFrequencyCalculator()
        self._decay_calc  = EngagementDecayCalculator()
        self._neg_calc    = NegativeSignalCalculator()
        self._conc_calc   = ContactConcentrationCalculator()
        self._rec_calc    = RecencyCalculator()

    def compute(
        self,
        account_id: str,
        account_domain: str,
        outreach_rows: list[OutreachDaySummary],
        account_segment: str = "DEFAULT",
        as_of: datetime | None = None,
    ) -> AccountFatigueScore:
        """Compute the composite fatigue score for one account.

        Args:
            account_id:      Account UUID string.
            account_domain:  Normalised company domain.
            outreach_rows:   All outreach records for this account (any window;
                             each calculator filters to its own window internally).
            account_segment: One of ENTERPRISE | MID_MARKET | SMB | DEFAULT.
            as_of:           Reference timestamp (defaults to UTC now).

        Returns:
            AccountFatigueScore with all components populated.
        """
        as_of = as_of or datetime.now(timezone.utc)
        weights = self._weights_override or _resolve_weights(account_segment)

        component_results: list[tuple[str, ComponentResult]] = [
            (
                "outreach_frequency",
                self._freq_calc.compute(
                    outreach_rows, as_of, account_segment=account_segment
                ),
            ),
            (
                "engagement_decay",
                self._decay_calc.compute(outreach_rows, as_of),
            ),
            (
                "negative_signal",
                self._neg_calc.compute(outreach_rows, as_of),
            ),
            (
                "contact_concentration",
                self._conc_calc.compute(outreach_rows, as_of),
            ),
            (
                "recency",
                self._rec_calc.compute(outreach_rows, as_of),
            ),
        ]

        components: list[FatigueComponent] = []
        composite = 0.0
        for name, result in component_results:
            w = weights.get(name, 0.0)
            components.append(
                FatigueComponent(
                    name=name,
                    score=result.score,
                    weight=w,
                    breakdown=result.breakdown,
                )
            )
            composite += result.score * w

        composite = max(0.0, min(100.0, composite))
        severity  = _classify_severity(composite)

        logger.debug(
            "account=%s segment=%s fatigue=%.1f severity=%s",
            account_domain, account_segment, composite, severity.value,
        )

        return AccountFatigueScore(
            account_id=account_id,
            account_domain=account_domain,
            score=round(composite, 2),
            severity=severity,
            components=components,
            computed_at=as_of,
            account_segment=account_segment,
        )
