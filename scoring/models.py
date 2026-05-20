"""Shared scoring domain models for harmoni.

Defines the canonical output types for the Intent Network Model, Churn
Predictor, and Account Fatigue Score engine, plus the intermediate
AccountFeatureVector and input signal/outreach types used by the feature
engineering pipelines.

All types are plain dataclasses — no ORM, no serialization magic.
Database persistence is handled by scoring.repository.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class ScoreType(str, Enum):
    INTENT = "INTENT"
    CHURN = "CHURN"
    FATIGUE = "FATIGUE"


class ChurnRiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class FatigueSeverity(str, Enum):
    """Cognitive-load tier of a buying committee.

    Distinct from ChurnRiskLevel even though the values are the same:
    fatigue describes over-contact risk; churn describes deal-loss risk.
    """
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# ---------------------------------------------------------------------------
# Feature engineering inputs
# ---------------------------------------------------------------------------


@dataclass
class OutreachDaySummary:
    """Aggregated daily outreach sent TO a buying committee member.

    One row per (member_id, channel, sent_date). Used by the Account Fatigue
    Score engine — captures outreach frequency, engagement responses, and
    negative opt-out signals from the sender's perspective.
    """

    sent_date: datetime
    member_id: str
    channel: str                       # EMAIL | LINKEDIN | PHONE | DIRECT_MAIL

    # Volume
    sent_count: int = 0

    # Engagement responses
    opened_count: int = 0
    clicked_count: int = 0
    replied_count: int = 0
    meaningful_reply_count: int = 0    # substantive reply (not auto-response)

    # Negative / opt-out signals
    bounced_count: int = 0
    unsubscribed_count: int = 0
    spam_reported_count: int = 0


@dataclass
class SignalRow:
    """One aggregated row from fct_account_signal_hourly (or a daily rollup).

    All counts refer to a single (account, signal_date, source_system) grain.
    """

    signal_date: datetime
    source_system: str                # WEB | EMAIL | CRM | WEBINAR
    signal_count: int = 0
    strong_signal_count: int = 0
    high_intent_signal_count: int = 0
    negative_signal_count: int = 0
    unique_member_count: int = 0
    total_strength_score: float = 0.0


@dataclass
class MemberEngagementRow:
    """One row from fct_committee_engagement (daily per-member per-channel)."""

    signal_date: datetime
    member_id: str
    seniority_level: str              # C_SUITE | VP | DIRECTOR | MANAGER | IC
    role_weight: float                # 0.0–1.0
    signal_count: int = 0
    weighted_signal_score: float = 0.0
    high_intent_count: int = 0
    negative_count: int = 0


# ---------------------------------------------------------------------------
# Feature vector — the computed representation fed to ML models
# ---------------------------------------------------------------------------

# Ordered list used for sklearn array construction and model I/O contracts.
FEATURE_NAMES: list[str] = [
    "total_signals_7d",
    "total_signals_14d",
    "total_signals_30d",
    "strong_signals_7d",
    "strong_signals_14d",
    "high_intent_signals_7d",
    "high_intent_signals_14d",
    "negative_signals_7d",
    "negative_signals_30d",
    "unique_members_7d",
    "unique_members_30d",
    "channel_count_7d",
    "role_weighted_score_7d",
    "c_suite_vp_signals_7d",
    "committee_coverage_pct_30d",
    "velocity_7d",
    "velocity_14d",
    "days_since_last_signal",
    "decayed_score_7d",
]


@dataclass
class AccountFeatureVector:
    """Numeric feature representation for one account at one point in time.

    All window sizes are in calendar days relative to ``as_of``.
    """

    account_id: str
    account_domain: str
    as_of: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # ---- Volume features ----
    total_signals_7d: int = 0
    total_signals_14d: int = 0
    total_signals_30d: int = 0
    strong_signals_7d: int = 0
    strong_signals_14d: int = 0
    high_intent_signals_7d: int = 0
    high_intent_signals_14d: int = 0
    negative_signals_7d: int = 0
    negative_signals_30d: int = 0

    # ---- Member engagement features ----
    unique_members_7d: int = 0
    unique_members_30d: int = 0
    channel_count_7d: int = 0          # number of distinct source_systems active in 7d

    # ---- Role-weighted features ----
    role_weighted_score_7d: float = 0.0
    c_suite_vp_signals_7d: int = 0

    # ---- Committee coverage ----
    committee_coverage_pct_30d: float = 0.0  # % of known members who signalled

    # ---- Velocity (signal acceleration) ----
    velocity_7d: float = 0.0    # (7d count / prior_7d count) - 1; clamped to [-1, 5]
    velocity_14d: float = 0.0

    # ---- Recency ----
    days_since_last_signal: float = 999.0  # large if never signalled

    # ---- Decay-weighted score ----
    decayed_score_7d: float = 0.0     # Σ strength_score_i * exp(-λ * days_old_i)

    def to_feature_array(self) -> list[float]:
        """Return ordered feature values matching FEATURE_NAMES."""
        return [float(getattr(self, name)) for name in FEATURE_NAMES]

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict (for JSONB storage in account_scores)."""
        d: dict[str, Any] = {}
        for f in fields(self):
            val = getattr(self, f.name)
            if isinstance(val, datetime):
                d[f.name] = val.isoformat()
            else:
                d[f.name] = val
        return d


# ---------------------------------------------------------------------------
# Model outputs
# ---------------------------------------------------------------------------


@dataclass
class IntentScore:
    """Account-level consolidated intent score (0–100).

    Produced by IntentNetworkModel. Higher score = stronger buying intent.
    Confidence reflects the model's certainty (informed by signal volume).
    """

    account_id: str
    account_domain: str
    score: float                        # 0.0–100.0
    confidence: float                   # 0.0–1.0
    signal_breakdown: dict[str, Any] = field(default_factory=dict)
    model_version: str = "unknown"
    computed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if not (0.0 <= self.score <= 100.0):
            raise ValueError(f"IntentScore.score must be 0–100, got {self.score}")
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"IntentScore.confidence must be 0–1, got {self.confidence}")

    @property
    def is_high_intent(self) -> bool:
        return self.score >= 70.0

    @property
    def score_type(self) -> ScoreType:
        return ScoreType.INTENT


@dataclass
class ChurnPrediction:
    """Account-level 30-day deal abandonment probability.

    Produced by ChurnPredictor. churn_probability ∈ [0, 1].
    risk_level is a categorical tier derived from probability thresholds.
    """

    account_id: str
    account_domain: str
    churn_probability: float            # 0.0–1.0
    risk_level: ChurnRiskLevel
    signal_breakdown: dict[str, Any] = field(default_factory=dict)
    model_version: str = "unknown"
    computed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    prediction_window_days: int = 30

    def __post_init__(self) -> None:
        if not (0.0 <= self.churn_probability <= 1.0):
            raise ValueError(
                f"ChurnPrediction.churn_probability must be 0–1, got {self.churn_probability}"
            )

    @property
    def score_type(self) -> ScoreType:
        return ScoreType.CHURN

    @property
    def is_high_risk(self) -> bool:
        return self.risk_level in (ChurnRiskLevel.HIGH, ChurnRiskLevel.CRITICAL)


# ---------------------------------------------------------------------------
# Fatigue scoring types
# ---------------------------------------------------------------------------


@dataclass
class FatigueComponent:
    """Scored output of one fatigue dimension calculator.

    score ∈ [0, 100]: higher = more fatigue contributed by this dimension.
    weight: this component's contribution to the composite score (all weights
    across all components for one account sum to 1.0).
    """

    name: str
    score: float        # 0.0–100.0
    weight: float       # 0.0–1.0
    breakdown: dict[str, Any] = field(default_factory=dict)

    @property
    def weighted_score(self) -> float:
        return self.score * self.weight


@dataclass
class AccountFatigueScore:
    """Composite account-level cognitive-load score (0–100).

    Produced by FatigueScoreEngine. Higher score = more fatigued committee.
    Drives ActionCooldown logic in the NBA orchestrator.
    """

    account_id: str
    account_domain: str
    score: float                    # 0.0–100.0
    severity: FatigueSeverity
    components: list[FatigueComponent] = field(default_factory=list)
    computed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    account_segment: str = "DEFAULT"

    def __post_init__(self) -> None:
        if not (0.0 <= self.score <= 100.0):
            raise ValueError(f"AccountFatigueScore.score must be 0–100, got {self.score}")

    @property
    def score_type(self) -> ScoreType:
        return ScoreType.FATIGUE

    @property
    def is_over_threshold(self) -> bool:
        """True when severity is HIGH or CRITICAL — triggers cooldown."""
        return self.severity in (FatigueSeverity.HIGH, FatigueSeverity.CRITICAL)

    def component_by_name(self, name: str) -> "FatigueComponent | None":
        return next((c for c in self.components if c.name == name), None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "account_id": self.account_id,
            "account_domain": self.account_domain,
            "score": round(self.score, 2),
            "severity": self.severity.value,
            "account_segment": self.account_segment,
            "computed_at": self.computed_at.isoformat(),
            "components": [
                {
                    "name": c.name,
                    "score": round(c.score, 2),
                    "weight": c.weight,
                    "weighted_score": round(c.weighted_score, 2),
                    "breakdown": c.breakdown,
                }
                for c in self.components
            ],
        }


@dataclass
class CooldownEntry:
    """A Redis-backed cooldown lock for an account or committee member.

    Returned by ActionCooldownEngine.get_cooldown_info() for diagnostics.
    Not persisted to database — the account_cooldowns table is the audit trail.
    """

    entity_type: str            # 'account' | 'member'
    entity_id: str
    severity: FatigueSeverity
    ttl_seconds: int            # remaining TTL as of query time
