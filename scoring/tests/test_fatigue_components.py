"""Tests for scoring.fatigue.components — all five fatigue calculators."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from scoring.fatigue.components import (
    ContactConcentrationCalculator,
    EngagementDecayCalculator,
    NegativeSignalCalculator,
    OutreachFrequencyCalculator,
    RecencyCalculator,
    _FREQUENCY_BASELINES,
    _FREQUENCY_SATURATION_MULTIPLE,
    _NEGATIVE_SATURATION_RATE,
    _NEGATIVE_WEIGHTS,
)
from scoring.models import OutreachDaySummary

_NOW = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row(
    days_ago: float,
    member_id: str = "m1",
    channel: str = "EMAIL",
    *,
    sent: int = 1,
    opened: int = 0,
    clicked: int = 0,
    replied: int = 0,
    meaningful_reply: int = 0,
    bounced: int = 0,
    unsubscribed: int = 0,
    spam: int = 0,
) -> OutreachDaySummary:
    return OutreachDaySummary(
        sent_date=_NOW - timedelta(days=days_ago),
        member_id=member_id,
        channel=channel,
        sent_count=sent,
        opened_count=opened,
        clicked_count=clicked,
        replied_count=replied,
        meaningful_reply_count=meaningful_reply,
        bounced_count=bounced,
        unsubscribed_count=unsubscribed,
        spam_reported_count=spam,
    )


# ===========================================================================
# 1. OutreachFrequencyCalculator
# ===========================================================================


class TestOutreachFrequencyCalculator:
    def setup_method(self):
        self.calc = OutreachFrequencyCalculator()

    def test_zero_outreach_returns_zero(self):
        result = self.calc.compute([], _NOW)
        assert result.score == 0.0

    def test_score_in_range(self):
        rows = [_row(i, sent=3) for i in range(7)]
        result = self.calc.compute(rows, _NOW)
        assert 0.0 <= result.score <= 100.0

    def test_saturation_at_multiple(self):
        # 2.5× the DEFAULT baseline (4/week) = 10 sends in 7d → score = 100
        baseline = _FREQUENCY_BASELINES["DEFAULT"]
        sat_sends = int(baseline * _FREQUENCY_SATURATION_MULTIPLE)
        rows = [_row(i % 7, sent=1) for i in range(sat_sends)]
        result = self.calc.compute(rows, _NOW, account_segment="DEFAULT")
        assert result.score == pytest.approx(100.0, abs=1.0)

    def test_exactly_at_baseline_scores_below_50(self):
        # Default baseline = 4/week
        rows = [_row(i, sent=1) for i in range(4)]
        result = self.calc.compute(rows, _NOW, account_segment="DEFAULT")
        # ratio = 4/4 = 1.0; score = 1.0/2.5 * 100 = 40
        assert result.score == pytest.approx(40.0, abs=1.0)

    def test_enterprise_lower_baseline(self):
        # Enterprise baseline = 2/week → same 4 sends = 2× baseline → higher score
        rows = [_row(i, sent=1) for i in range(4)]
        result_ent = self.calc.compute(rows, _NOW, account_segment="ENTERPRISE")
        result_smb = self.calc.compute(rows, _NOW, account_segment="SMB")
        assert result_ent.score > result_smb.score

    def test_breakdown_contains_required_keys(self):
        result = self.calc.compute([_row(1, sent=3)], _NOW)
        assert "sent_7d" in result.breakdown
        assert "baseline_weekly" in result.breakdown
        assert "frequency_ratio" in result.breakdown

    def test_outreach_outside_7d_not_counted_in_7d(self):
        # Signal from 10 days ago should not count toward sent_7d
        old = _row(10.0, sent=50)
        result = self.calc.compute([old], _NOW)
        assert result.breakdown["sent_7d"] == 0
        assert result.score == 0.0


# ===========================================================================
# 2. EngagementDecayCalculator
# ===========================================================================


class TestEngagementDecayCalculator:
    def setup_method(self):
        self.calc = EngagementDecayCalculator()

    def test_empty_rows_returns_zero(self):
        result = self.calc.compute([], _NOW)
        assert result.score == 0.0

    def test_no_prior_window_returns_zero(self):
        # Only recent sends — no baseline to compare
        recent = [_row(1, sent=5, opened=3)]
        result = self.calc.compute(recent, _NOW)
        assert result.score == 0.0

    def test_stable_engagement_returns_zero(self):
        recent = [_row(3, sent=10, opened=6, clicked=2)]
        prior  = [_row(15, sent=10, opened=6, clicked=2)]
        result = self.calc.compute(recent + prior, _NOW)
        assert result.score == pytest.approx(0.0, abs=1.0)

    def test_full_decay_scores_100(self):
        # Engagement was 80% historically, now 0%
        prior  = [_row(20, sent=10, opened=8)]
        recent = [_row(2, sent=10, opened=0)]
        result = self.calc.compute(recent + prior, _NOW)
        assert result.score == pytest.approx(100.0, abs=1.0)

    def test_partial_decay_scores_proportionally(self):
        # Prior rate = 80%, recent rate = 40% → decay ratio = 1 - 0.4/0.8 = 0.5 → score 50
        prior  = [_row(20, sent=10, opened=8)]
        recent = [_row(2, sent=10, opened=4)]
        result = self.calc.compute(recent + prior, _NOW)
        assert result.score == pytest.approx(50.0, abs=1.0)

    def test_no_sends_in_recent_window_returns_zero(self):
        # All sends are older than 7d → no recent window
        prior = [_row(15, sent=10, opened=5)]
        result = self.calc.compute(prior, _NOW)
        assert result.score == 0.0

    def test_breakdown_has_engagement_rates(self):
        rows = [_row(3, sent=5, opened=2), _row(15, sent=5, opened=3)]
        result = self.calc.compute(rows, _NOW)
        assert "recent_engagement_rate" in result.breakdown
        assert "prior_engagement_rate" in result.breakdown
        assert "decay_ratio" in result.breakdown


# ===========================================================================
# 3. NegativeSignalCalculator
# ===========================================================================


class TestNegativeSignalCalculator:
    def setup_method(self):
        self.calc = NegativeSignalCalculator()

    def test_no_negatives_returns_zero(self):
        rows = [_row(i, sent=5, opened=3) for i in range(7)]
        result = self.calc.compute(rows, _NOW)
        assert result.score == 0.0

    def test_empty_rows_returns_zero(self):
        assert self.calc.compute([], _NOW).score == 0.0

    def test_spam_weighted_highest(self):
        # 1 spam vs 1 unsubscribe vs 1 bounce — spam should produce highest score
        spam = self.calc.compute([_row(1, sent=10, spam=1)], _NOW)
        unsub = self.calc.compute([_row(1, sent=10, unsubscribed=1)], _NOW)
        bounce = self.calc.compute([_row(1, sent=10, bounced=1)], _NOW)
        assert spam.score > unsub.score > bounce.score

    def test_score_capped_at_100(self):
        rows = [_row(i, sent=1, unsubscribed=1, spam=1) for i in range(30)]
        result = self.calc.compute(rows, _NOW)
        assert result.score <= 100.0

    def test_negatives_outside_30d_not_counted(self):
        old  = _row(31.0, sent=5, unsubscribed=5)
        result = self.calc.compute([old], _NOW)
        assert result.score == 0.0

    def test_weighted_rate_at_saturation_gives_100(self):
        # saturation rate = 0.20 → weighted_count / sent = 0.20 at saturation
        # spam weight = 5.0 → 1 spam / 25 sent = 0.04 → 0.04 * 5 = 0.20 weighted rate
        rows = [_row(1, sent=25, spam=1)]
        result = self.calc.compute(rows, _NOW)
        assert result.score == pytest.approx(100.0, abs=0.1)

    @pytest.mark.parametrize("sent,spam,expected_min", [
        (100, 0, 0.0),
        (100, 1, 5.0),   # 1/100 * 5.0 weight = 0.05 rate → 25% of sat → score 25
        (10, 1, 50.0),   # 1/10 * 5.0 = 0.5 weighted rate → 250% of sat → capped 100
    ])
    def test_parametrized_spam_scenarios(self, sent, spam, expected_min):
        rows = [_row(1, sent=sent, spam=spam)]
        result = self.calc.compute(rows, _NOW)
        assert result.score >= expected_min

    def test_breakdown_has_counts(self):
        rows = [_row(1, sent=10, unsubscribed=1, spam=0, bounced=1)]
        result = self.calc.compute(rows, _NOW)
        assert "unsubscribed_30d" in result.breakdown
        assert "spam_reported_30d" in result.breakdown
        assert "bounced_30d" in result.breakdown


# ===========================================================================
# 4. ContactConcentrationCalculator
# ===========================================================================


class TestContactConcentrationCalculator:
    def setup_method(self):
        self.calc = ContactConcentrationCalculator()

    def test_empty_rows_returns_zero(self):
        result = self.calc.compute([], _NOW)
        assert result.score == 0.0

    def test_single_member_returns_zero(self):
        rows = [_row(i, member_id="m1", sent=5) for i in range(10)]
        result = self.calc.compute(rows, _NOW)
        assert result.score == 0.0

    def test_perfectly_even_distribution_returns_zero(self):
        rows = [
            _row(1, member_id="m1", sent=10),
            _row(2, member_id="m2", sent=10),
            _row(3, member_id="m3", sent=10),
        ]
        result = self.calc.compute(rows, _NOW)
        assert result.score == pytest.approx(0.0, abs=0.1)

    def test_all_to_one_member_returns_100(self):
        rows = [
            _row(1, member_id="m1", sent=100),
            _row(2, member_id="m2", sent=0),   # no sends (won't appear in per_member if sent=0)
        ]
        # Actually with sent=0 the row contributes 0, only m1 counts
        # → single member case → 0. Let's use a real 2-member with all to m1
        rows2 = [
            _row(1, member_id="m1", sent=100),
            _row(2, member_id="m2", sent=1),   # tiny amount to m2
        ]
        result = self.calc.compute(rows2, _NOW)
        # Should be very high (close to 100)
        assert result.score > 80.0

    def test_all_outreach_to_one_of_two_members(self):
        rows = [
            _row(1, member_id="m1", sent=10),
            _row(2, member_id="m2", sent=0),  # 0 sends — effectively single member
        ]
        # Only m1 has sends → single member, score = 0
        result = self.calc.compute(rows, _NOW)
        assert result.score == 0.0

    def test_two_members_equal_distribution_is_zero(self):
        rows = [
            _row(1, member_id="m1", sent=5),
            _row(2, member_id="m2", sent=5),
        ]
        result = self.calc.compute(rows, _NOW)
        assert result.score == pytest.approx(0.0, abs=0.1)

    def test_outside_30d_rows_excluded(self):
        old_rows = [_row(31, member_id="m1", sent=100)]
        recent   = [_row(1, member_id="m2", sent=10)]
        result   = self.calc.compute(old_rows + recent, _NOW)
        # Only m2 visible in 30d → single member → score = 0
        assert result.score == 0.0

    def test_breakdown_has_member_count(self):
        rows = [
            _row(1, member_id="m1", sent=5),
            _row(2, member_id="m2", sent=5),
        ]
        result = self.calc.compute(rows, _NOW)
        assert "unique_members_contacted_30d" in result.breakdown
        assert result.breakdown["unique_members_contacted_30d"] == 2


# ===========================================================================
# 5. RecencyCalculator
# ===========================================================================


class TestRecencyCalculator:
    def setup_method(self):
        self.calc = RecencyCalculator()

    def test_no_outreach_returns_zero(self):
        result = self.calc.compute([], _NOW)
        assert result.score == 0.0

    def test_no_outreach_in_30d_returns_zero(self):
        old = _row(40, sent=5, meaningful_reply=2)
        result = self.calc.compute([old], _NOW)
        assert result.score == 0.0

    def test_recent_meaningful_reply_returns_zero(self):
        rows = [
            _row(3, sent=5),
            _row(3, sent=0, meaningful_reply=1),
        ]
        result = self.calc.compute(rows, _NOW)
        assert result.score == 0.0

    def test_no_meaningful_reply_returns_80(self):
        rows = [_row(i, sent=3) for i in range(10)]
        result = self.calc.compute(rows, _NOW)
        assert result.score == pytest.approx(80.0)

    def test_score_rises_as_reply_ages(self):
        rows_fresh = [_row(1, sent=5), _row(8, sent=0, meaningful_reply=1)]
        rows_old   = [_row(1, sent=5), _row(25, sent=0, meaningful_reply=1)]
        r_fresh = self.calc.compute(rows_fresh, _NOW)
        r_old   = self.calc.compute(rows_old, _NOW)
        assert r_old.score > r_fresh.score

    def test_score_bounded_at_70_with_reply(self):
        # Meaningful reply 30+ days ago (at the edge) → score ≤ 70
        rows = [
            _row(1, sent=5),
            _row(29, sent=0, meaningful_reply=1),
        ]
        result = self.calc.compute(rows, _NOW)
        assert result.score <= 70.0

    def test_breakdown_days_since_reply(self):
        rows = [
            _row(1, sent=5),
            _row(10, sent=0, meaningful_reply=1),
        ]
        result = self.calc.compute(rows, _NOW)
        assert result.breakdown["days_since_meaningful_reply"] == pytest.approx(10.0, abs=0.1)
