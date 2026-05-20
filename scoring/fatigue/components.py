"""Fatigue component calculators for the Account Fatigue Score engine.

Each calculator is a single-responsibility class with one public method:
    compute(outreach_rows, as_of) -> ComponentResult

The five components and their fatigue signals:

1. OutreachFrequencyCalculator  — messages sent per week vs. segment baseline.
2. EngagementDecayCalculator    — falling open/click/reply rate trend.
3. NegativeSignalCalculator     — unsubscribes, spam reports, bounces.
4. ContactConcentrationCalculator — over-reliance on a single committee member.
5. RecencyCalculator            — time since last meaningful reply or meeting.

All scores are on a 0–100 scale (higher = more fatigue contributed).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from scoring.models import OutreachDaySummary


# ---------------------------------------------------------------------------
# ComponentResult — return type for all calculators
# ---------------------------------------------------------------------------


@dataclass
class ComponentResult:
    """Output of one fatigue dimension calculator."""

    score: float                           # 0.0–100.0
    breakdown: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 1. Outreach Frequency Calculator
# ---------------------------------------------------------------------------

# Weekly send-rate baselines (messages per week) per account segment.
_FREQUENCY_BASELINES: dict[str, float] = {
    "ENTERPRISE":  2.0,
    "MID_MARKET":  4.0,
    "SMB":         6.0,
    "DEFAULT":     4.0,
}

# At this many times the baseline, score saturates at 100.
_FREQUENCY_SATURATION_MULTIPLE = 2.5


class OutreachFrequencyCalculator:
    """Score based on outreach volume relative to the account segment baseline.

    Sends at the weekly baseline → score ≈ 40 (moderate load).
    Sends at 2.5× baseline    → score = 100 (maximum fatigue from volume).
    Zero sends                → score = 0.
    """

    def compute(
        self,
        outreach_rows: list[OutreachDaySummary],
        as_of: datetime | None = None,
        *,
        account_segment: str = "DEFAULT",
    ) -> ComponentResult:
        as_of = as_of or datetime.now(timezone.utc)
        t7  = as_of - timedelta(days=7)
        t14 = as_of - timedelta(days=14)

        sent_7d  = sum(r.sent_count for r in outreach_rows if r.sent_date >= t7)
        sent_14d = sum(r.sent_count for r in outreach_rows if r.sent_date >= t14)

        baseline_weekly = _FREQUENCY_BASELINES.get(account_segment, _FREQUENCY_BASELINES["DEFAULT"])
        # Convert 7-day count to a weekly rate for comparison
        actual_weekly = sent_7d  # already a 7-day window ≈ weekly rate

        ratio = actual_weekly / baseline_weekly if baseline_weekly > 0 else 0.0
        # Linear ramp: ratio 0 → score 0; ratio at saturation multiple → score 100
        score = min(100.0, (ratio / _FREQUENCY_SATURATION_MULTIPLE) * 100.0)

        return ComponentResult(
            score=round(score, 2),
            breakdown={
                "sent_7d": sent_7d,
                "sent_14d": sent_14d,
                "baseline_weekly": baseline_weekly,
                "actual_weekly": actual_weekly,
                "frequency_ratio": round(ratio, 3),
                "account_segment": account_segment,
            },
        )


# ---------------------------------------------------------------------------
# 2. Engagement Decay Calculator
# ---------------------------------------------------------------------------


class EngagementDecayCalculator:
    """Score based on how much engagement rates have fallen recently.

    Compares the engagement rate (opens + clicks + replies) in the last 7 days
    against the 8–30 day prior window. A significant drop signals fatigue.

    Stable or rising engagement → score = 0.
    Engagement dropped to zero despite ongoing outreach → score = 100.
    No outreach in the measured period → score = 0 (can't measure decay).
    """

    def compute(
        self,
        outreach_rows: list[OutreachDaySummary],
        as_of: datetime | None = None,
    ) -> ComponentResult:
        as_of = as_of or datetime.now(timezone.utc)
        t7  = as_of - timedelta(days=7)
        t30 = as_of - timedelta(days=30)

        recent = [r for r in outreach_rows if r.sent_date >= t7]
        prior  = [r for r in outreach_rows if t30 <= r.sent_date < t7]

        def _engagement_rate(rows: list[OutreachDaySummary]) -> float:
            sent = sum(r.sent_count for r in rows)
            if sent == 0:
                return 0.0
            engaged = sum(r.opened_count + r.clicked_count + r.replied_count for r in rows)
            return engaged / sent

        recent_rate = _engagement_rate(recent)
        prior_rate  = _engagement_rate(prior)

        recent_sent = sum(r.sent_count for r in recent)
        prior_sent  = sum(r.sent_count for r in prior)

        if prior_sent == 0 or prior_rate == 0.0:
            # No baseline to compare against — cannot measure decay
            score = 0.0
            decay_ratio = 0.0
        else:
            # How much worse is recent engagement vs. the prior window?
            decay_ratio = max(0.0, 1.0 - recent_rate / prior_rate)
            score = min(100.0, decay_ratio * 100.0)

        return ComponentResult(
            score=round(score, 2),
            breakdown={
                "recent_sent_7d": recent_sent,
                "prior_sent_8_30d": prior_sent,
                "recent_engagement_rate": round(recent_rate, 4),
                "prior_engagement_rate": round(prior_rate, 4),
                "decay_ratio": round(decay_ratio, 4),
            },
        )


# ---------------------------------------------------------------------------
# 3. Negative Signal Calculator
# ---------------------------------------------------------------------------

# Per-event severity weights (applied to rate, not raw count)
_NEGATIVE_WEIGHTS: dict[str, float] = {
    "unsubscribed": 3.0,   # deliberate opt-out — strongest signal
    "spam_reported": 5.0,  # explicit rejection — most severe
    "bounced": 1.0,        # deliverability issue — weakest negative
}

# Score saturates at this weighted rate (as a % of sent volume)
_NEGATIVE_SATURATION_RATE = 0.20   # 20% weighted negative rate → score 100


class NegativeSignalCalculator:
    """Score based on unsubscribes, spam reports, and bounces in the last 30 days.

    Rates are normalized by sent volume to avoid penalizing high-outreach accounts
    unfairly for the same absolute negative count as low-outreach accounts.

    Zero negatives          → score = 0.
    ≥20% weighted neg. rate → score = 100.
    """

    def compute(
        self,
        outreach_rows: list[OutreachDaySummary],
        as_of: datetime | None = None,
    ) -> ComponentResult:
        as_of = as_of or datetime.now(timezone.utc)
        t30 = as_of - timedelta(days=30)

        rows_30d = [r for r in outreach_rows if r.sent_date >= t30]

        sent_30d    = sum(r.sent_count       for r in rows_30d)
        unsubs_30d  = sum(r.unsubscribed_count  for r in rows_30d)
        spam_30d    = sum(r.spam_reported_count for r in rows_30d)
        bounces_30d = sum(r.bounced_count       for r in rows_30d)

        if sent_30d == 0:
            score = 0.0
            weighted_rate = 0.0
        else:
            weighted_count = (
                unsubs_30d  * _NEGATIVE_WEIGHTS["unsubscribed"]
                + spam_30d  * _NEGATIVE_WEIGHTS["spam_reported"]
                + bounces_30d * _NEGATIVE_WEIGHTS["bounced"]
            )
            weighted_rate = weighted_count / sent_30d
            score = min(100.0, (weighted_rate / _NEGATIVE_SATURATION_RATE) * 100.0)

        return ComponentResult(
            score=round(score, 2),
            breakdown={
                "sent_30d": sent_30d,
                "unsubscribed_30d": unsubs_30d,
                "spam_reported_30d": spam_30d,
                "bounced_30d": bounces_30d,
                "weighted_negative_rate": round(weighted_rate, 4),
                "saturation_rate": _NEGATIVE_SATURATION_RATE,
            },
        )


# ---------------------------------------------------------------------------
# 4. Contact Concentration Calculator
# ---------------------------------------------------------------------------


class ContactConcentrationCalculator:
    """Score based on how concentrated outreach is on a single committee member.

    Uses the normalised Herfindahl-Hirschman Index (HHI):
        HHI      = Σ(share_i²)       range: [1/n, 1.0]
        HHI_norm = (HHI − 1/n) / (1 − 1/n)   range: [0.0, 1.0]

    HHI_norm = 0 → perfectly even distribution → score = 0.
    HHI_norm = 1 → all outreach to one member  → score = 100.

    Zero or one unique member → score = 0 (no multi-member baseline to compare).
    """

    def compute(
        self,
        outreach_rows: list[OutreachDaySummary],
        as_of: datetime | None = None,
    ) -> ComponentResult:
        as_of = as_of or datetime.now(timezone.utc)
        t30 = as_of - timedelta(days=30)

        rows_30d = [r for r in outreach_rows if r.sent_date >= t30]

        # Aggregate sent count per member
        per_member: dict[str, int] = {}
        for r in rows_30d:
            per_member[r.member_id] = per_member.get(r.member_id, 0) + r.sent_count

        total = sum(per_member.values())
        n_members = len(per_member)

        if total == 0 or n_members <= 1:
            return ComponentResult(
                score=0.0,
                breakdown={
                    "unique_members_contacted_30d": n_members,
                    "total_sent_30d": total,
                    "hhi_normalized": 0.0,
                    "note": "single or no member — concentration not applicable",
                },
            )

        shares = [count / total for count in per_member.values()]
        hhi = sum(s ** 2 for s in shares)
        hhi_min = 1.0 / n_members
        # Avoid divide-by-zero when n=1 (already handled above)
        hhi_norm = (hhi - hhi_min) / (1.0 - hhi_min)
        score = min(100.0, hhi_norm * 100.0)

        return ComponentResult(
            score=round(score, 2),
            breakdown={
                "unique_members_contacted_30d": n_members,
                "total_sent_30d": total,
                "per_member_counts": per_member,
                "hhi_raw": round(hhi, 4),
                "hhi_normalized": round(hhi_norm, 4),
            },
        )


# ---------------------------------------------------------------------------
# 5. Recency Calculator
# ---------------------------------------------------------------------------

# Days after last meaningful reply at which score reaches its maximum
_RECENCY_MAX_DAYS = 30.0
# Score returned when there has been outreach but zero meaningful replies ever
_RECENCY_NO_REPLY_SCORE = 80.0
# Score when there is no outreach in the lookback window (can't measure)
_RECENCY_NO_OUTREACH_SCORE = 0.0


class RecencyCalculator:
    """Score based on time since the last meaningful reply or meeting.

    A "meaningful reply" is one where `meaningful_reply_count > 0`.

    No outreach in 30d              → score = 0 (not measuring a fatigued state)
    Meaningful reply within 7d      → score = 0 (fresh engagement)
    Meaningful reply 7–30d ago      → score scales linearly 0→70
    Outreach sent but no reply ever → score = 80 (persistent non-response)
    No outreach + no reply          → score = 0
    """

    def compute(
        self,
        outreach_rows: list[OutreachDaySummary],
        as_of: datetime | None = None,
    ) -> ComponentResult:
        as_of = as_of or datetime.now(timezone.utc)
        t30 = as_of - timedelta(days=30)

        rows_30d = [r for r in outreach_rows if r.sent_date >= t30]
        sent_30d = sum(r.sent_count for r in rows_30d)

        if sent_30d == 0:
            return ComponentResult(
                score=_RECENCY_NO_OUTREACH_SCORE,
                breakdown={
                    "sent_30d": 0,
                    "days_since_meaningful_reply": None,
                    "note": "no outreach — recency not applicable",
                },
            )

        # Find the most recent meaningful reply across all time
        reply_dates = [
            r.sent_date for r in outreach_rows
            if r.meaningful_reply_count > 0
        ]

        if not reply_dates:
            return ComponentResult(
                score=_RECENCY_NO_REPLY_SCORE,
                breakdown={
                    "sent_30d": sent_30d,
                    "days_since_meaningful_reply": None,
                    "note": "outreach sent but no meaningful reply on record",
                },
            )

        last_reply = max(reply_dates)
        days_since = max(0.0, (as_of - last_reply).total_seconds() / 86400.0)

        if days_since <= 7.0:
            score = 0.0
        else:
            # Linear scale from 0 (at 7d) to 70 (at _RECENCY_MAX_DAYS)
            score = min(70.0, ((days_since - 7.0) / (_RECENCY_MAX_DAYS - 7.0)) * 70.0)

        return ComponentResult(
            score=round(score, 2),
            breakdown={
                "sent_30d": sent_30d,
                "days_since_meaningful_reply": round(days_since, 1),
                "last_meaningful_reply_date": last_reply.isoformat(),
            },
        )
