"""Feature engineering pipeline for the Intent Network Model.

FeatureEngineer transforms raw signal rows (from fct_account_signal_hourly
and fct_committee_engagement) into a dense AccountFeatureVector suitable
for the logistic regression classifier.

Feature design (per ADR and PLAN.md):

1. Signal recency decay — exponential decay with 7-day half-life.
   decay_factor = exp(-λ * days_old)  where  λ = ln(2) / 7 ≈ 0.099.

2. Role-weighted aggregation — each signal is weighted by the member's
   role_weight (C_SUITE=1.0, VP=0.8, DIRECTOR=0.6, MANAGER=0.4, IC=0.2).

3. Channel diversity — channel_count_7d (number of distinct source channels
   active in the last 7 days). Used as a raw feature; the model learns its
   weight during training rather than applying a hard bonus.

4. Velocity — (N_current_window / N_prior_window) − 1, clamped to [−1, 5].
   Zero when no prior-window signals exist to avoid division-by-zero noise.

All time windows are computed relative to ``as_of`` (defaults to UTC now).
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any

from scoring.models import (
    AccountFeatureVector,
    MemberEngagementRow,
    SignalRow,
)

# 7-day half-life decay constant
_DECAY_LAMBDA: float = math.log(2) / 7.0

# Velocity clamp bounds
_VELOCITY_MIN: float = -1.0
_VELOCITY_MAX: float = 5.0

# Seniority levels that count as "senior" for c_suite_vp_signals_7d
_SENIOR_SENIORITY: frozenset[str] = frozenset({"C_SUITE", "VP"})


class FeatureEngineer:
    """Compute AccountFeatureVector from raw aggregated signal data.

    Args:
        decay_lambda: Recency decay rate (default: ln(2)/7 = 7-day half-life).
    """

    def __init__(self, decay_lambda: float = _DECAY_LAMBDA) -> None:
        self._lambda = decay_lambda

    def compute(
        self,
        account_id: str,
        account_domain: str,
        signals: list[SignalRow],
        member_signals: list[MemberEngagementRow],
        committee_size: int,
        as_of: datetime | None = None,
    ) -> AccountFeatureVector:
        """Compute the full feature vector for one account.

        Args:
            account_id:      Account UUID string.
            account_domain:  Normalised company domain.
            signals:         Daily aggregated signal rows (all channels).
            member_signals:  Daily per-member engagement rows.
            committee_size:  Total number of known committee members (active).
            as_of:           Reference timestamp (defaults to UTC now).

        Returns:
            Populated AccountFeatureVector.
        """
        as_of = as_of or datetime.now(timezone.utc)

        t7   = as_of - timedelta(days=7)
        t14  = as_of - timedelta(days=14)
        t30  = as_of - timedelta(days=30)

        # Filter signal rows by window
        s7   = [s for s in signals if s.signal_date >= t7]
        s14  = [s for s in signals if s.signal_date >= t14]
        s30  = [s for s in signals if s.signal_date >= t30]
        # Prior 7-day window (14d–7d ago) for velocity computation
        s_prior7 = [s for s in signals if t14 <= s.signal_date < t7]

        # ---- Volume features ----
        total_7d  = sum(s.signal_count for s in s7)
        total_14d = sum(s.signal_count for s in s14)
        total_30d = sum(s.signal_count for s in s30)

        strong_7d  = sum(s.strong_signal_count for s in s7)
        strong_14d = sum(s.strong_signal_count for s in s14)

        hi_7d  = sum(s.high_intent_signal_count for s in s7)
        hi_14d = sum(s.high_intent_signal_count for s in s14)

        neg_7d  = sum(s.negative_signal_count for s in s7)
        neg_30d = sum(s.negative_signal_count for s in s30)

        # ---- Member engagement features ----
        m7  = [m for m in member_signals if m.signal_date >= t7]
        m30 = [m for m in member_signals if m.signal_date >= t30]

        unique_members_7d  = len({m.member_id for m in m7})
        unique_members_30d = len({m.member_id for m in m30})

        channel_count_7d = len({s.source_system for s in s7})

        # ---- Role-weighted score (last 7 days) ----
        role_weighted_score_7d = sum(m.weighted_signal_score for m in m7)

        # ---- Senior stakeholder signal count (last 7 days) ----
        c_suite_vp_signals_7d = sum(
            m.signal_count for m in m7
            if m.seniority_level in _SENIOR_SENIORITY
        )

        # ---- Committee coverage (last 30 days) ----
        committee_coverage_pct_30d = (
            unique_members_30d / committee_size
            if committee_size > 0
            else 0.0
        )

        # ---- Velocity ----
        prior_7d_count = sum(s.signal_count for s in s_prior7)
        velocity_7d = _safe_velocity(total_7d, prior_7d_count)

        # Prior 14d window (28d–14d ago) for velocity_14d
        t28 = as_of - timedelta(days=28)
        s_prior14 = [s for s in signals if t28 <= s.signal_date < t14]
        prior_14d_count = sum(s.signal_count for s in s_prior14)
        velocity_14d = _safe_velocity(total_14d, prior_14d_count)

        # ---- Days since last signal ----
        all_signal_dates = [s.signal_date for s in signals if s.signal_count > 0]
        if all_signal_dates:
            last_signal = max(all_signal_dates)
            days_since = max(0.0, (as_of - last_signal).total_seconds() / 86400.0)
        else:
            days_since = 999.0

        # ---- Recency-decayed strength score (last 7 days) ----
        decayed_score_7d = _compute_decayed_score(s7, as_of, self._lambda)

        return AccountFeatureVector(
            account_id=account_id,
            account_domain=account_domain,
            as_of=as_of,
            total_signals_7d=total_7d,
            total_signals_14d=total_14d,
            total_signals_30d=total_30d,
            strong_signals_7d=strong_7d,
            strong_signals_14d=strong_14d,
            high_intent_signals_7d=hi_7d,
            high_intent_signals_14d=hi_14d,
            negative_signals_7d=neg_7d,
            negative_signals_30d=neg_30d,
            unique_members_7d=unique_members_7d,
            unique_members_30d=unique_members_30d,
            channel_count_7d=channel_count_7d,
            role_weighted_score_7d=role_weighted_score_7d,
            c_suite_vp_signals_7d=c_suite_vp_signals_7d,
            committee_coverage_pct_30d=min(1.0, committee_coverage_pct_30d),
            velocity_7d=velocity_7d,
            velocity_14d=velocity_14d,
            days_since_last_signal=days_since,
            decayed_score_7d=decayed_score_7d,
        )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _safe_velocity(current: int, prior: int) -> float:
    """Compute velocity clamped to [−1, 5]; 0.0 when prior is zero."""
    if prior == 0:
        return 0.0 if current == 0 else min(_VELOCITY_MAX, 1.0)
    raw = (current / prior) - 1.0
    return max(_VELOCITY_MIN, min(_VELOCITY_MAX, raw))


def _compute_decayed_score(
    signals: list[SignalRow],
    as_of: datetime,
    lam: float,
) -> float:
    """Sum of per-row total_strength_score weighted by recency decay."""
    total = 0.0
    for s in signals:
        days_old = max(0.0, (as_of - s.signal_date).total_seconds() / 86400.0)
        decay = math.exp(-lam * days_old)
        total += s.total_strength_score * decay
    return total
