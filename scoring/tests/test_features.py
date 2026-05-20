"""Tests for scoring.intent.features — FeatureEngineer and helpers."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from scoring.intent.features import (
    FeatureEngineer,
    _DECAY_LAMBDA,
    _compute_decayed_score,
    _safe_velocity,
)
from scoring.models import AccountFeatureVector, MemberEngagementRow, SignalRow

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


def _make_signal(
    days_ago: float,
    *,
    source_system: str = "WEB",
    signal_count: int = 5,
    strong_count: int = 2,
    hi_count: int = 1,
    neg_count: int = 0,
    strength_score: float = 10.0,
) -> SignalRow:
    return SignalRow(
        signal_date=_NOW - timedelta(days=days_ago),
        source_system=source_system,
        signal_count=signal_count,
        strong_signal_count=strong_count,
        high_intent_signal_count=hi_count,
        negative_signal_count=neg_count,
        unique_member_count=1,
        total_strength_score=strength_score,
    )


def _make_member(
    days_ago: float,
    member_id: str = "m1",
    seniority_level: str = "IC",
    role_weight: float = 0.2,
    signal_count: int = 3,
    weighted_score: float = 0.6,
) -> MemberEngagementRow:
    return MemberEngagementRow(
        signal_date=_NOW - timedelta(days=days_ago),
        member_id=member_id,
        seniority_level=seniority_level,
        role_weight=role_weight,
        signal_count=signal_count,
        weighted_signal_score=weighted_score,
    )


# ---------------------------------------------------------------------------
# _safe_velocity
# ---------------------------------------------------------------------------


class TestSafeVelocity:
    def test_positive_growth(self):
        assert _safe_velocity(20, 10) == pytest.approx(1.0)

    def test_decline(self):
        assert _safe_velocity(5, 10) == pytest.approx(-0.5)

    def test_zero_prior_zero_current(self):
        assert _safe_velocity(0, 0) == 0.0

    def test_zero_prior_nonzero_current(self):
        # No prior signals but some now → use max clamp of 1.0
        assert _safe_velocity(10, 0) == 1.0

    def test_clamp_max(self):
        # 60 vs 1 → 59, clamped at 5
        assert _safe_velocity(60, 1) == 5.0

    def test_clamp_min(self):
        # 0 vs 100 → -1.0 (already the minimum)
        assert _safe_velocity(0, 100) == -1.0

    def test_no_change(self):
        assert _safe_velocity(10, 10) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# _compute_decayed_score
# ---------------------------------------------------------------------------


class TestComputeDecayedScore:
    def test_zero_signals_returns_zero(self):
        assert _compute_decayed_score([], _NOW, _DECAY_LAMBDA) == 0.0

    def test_signal_today_is_undecayed(self):
        s = _make_signal(0, strength_score=100.0)
        result = _compute_decayed_score([s], _NOW, _DECAY_LAMBDA)
        assert result == pytest.approx(100.0, abs=0.01)

    def test_signal_at_half_life(self):
        # After 7 days, strength is halved
        s = _make_signal(7.0, strength_score=100.0)
        result = _compute_decayed_score([s], _NOW, _DECAY_LAMBDA)
        assert result == pytest.approx(50.0, abs=0.5)

    def test_additive_across_multiple_signals(self):
        s1 = _make_signal(0.0, strength_score=100.0)
        s2 = _make_signal(7.0, strength_score=100.0)
        result = _compute_decayed_score([s1, s2], _NOW, _DECAY_LAMBDA)
        assert result == pytest.approx(150.0, abs=1.0)

    def test_older_signal_contributes_less(self):
        s_fresh = _make_signal(1.0, strength_score=100.0)
        s_old   = _make_signal(6.0, strength_score=100.0)
        result = _compute_decayed_score([s_fresh, s_old], _NOW, _DECAY_LAMBDA)
        fresh_decay = 100.0 * math.exp(-_DECAY_LAMBDA * 1.0)
        old_decay   = 100.0 * math.exp(-_DECAY_LAMBDA * 6.0)
        assert result == pytest.approx(fresh_decay + old_decay, abs=0.01)


# ---------------------------------------------------------------------------
# FeatureEngineer.compute — window filtering
# ---------------------------------------------------------------------------


class TestFeatureEngineerWindowFiltering:
    def setup_method(self):
        self.fe = FeatureEngineer()

    def _compute(self, signals, members=None, committee_size=1):
        return self.fe.compute(
            "acct-1",
            "acme.com",
            signals,
            members or [],
            committee_size,
            as_of=_NOW,
        )

    def test_empty_signals_returns_defaults(self):
        fv = self._compute([])
        assert fv.total_signals_7d == 0
        assert fv.total_signals_30d == 0
        assert fv.days_since_last_signal == 999.0
        assert fv.decayed_score_7d == 0.0

    def test_signal_outside_30d_excluded_from_all_windows(self):
        old = _make_signal(31.0)
        fv = self._compute([old])
        assert fv.total_signals_30d == 0

    def test_signal_in_7d_included_in_all_windows(self):
        s = _make_signal(3.0, signal_count=10)
        fv = self._compute([s])
        assert fv.total_signals_7d == 10
        assert fv.total_signals_14d == 10
        assert fv.total_signals_30d == 10

    def test_signal_in_14d_but_not_7d(self):
        s = _make_signal(10.0, signal_count=7)
        fv = self._compute([s])
        assert fv.total_signals_7d == 0
        assert fv.total_signals_14d == 7
        assert fv.total_signals_30d == 7

    def test_strong_signals_counted_per_window(self):
        s = _make_signal(3.0, strong_count=4)
        fv = self._compute([s])
        assert fv.strong_signals_7d == 4
        assert fv.strong_signals_14d == 4

    def test_high_intent_signals_counted_per_window(self):
        s = _make_signal(10.0, hi_count=3)
        fv = self._compute([s])
        assert fv.high_intent_signals_7d == 0
        assert fv.high_intent_signals_14d == 3

    def test_negative_signals_in_30d(self):
        s1 = _make_signal(5.0, neg_count=2)
        s2 = _make_signal(25.0, neg_count=3)
        fv = self._compute([s1, s2])
        assert fv.negative_signals_7d == 2
        assert fv.negative_signals_30d == 5


# ---------------------------------------------------------------------------
# FeatureEngineer.compute — member / channel features
# ---------------------------------------------------------------------------


class TestFeatureEngineerMemberFeatures:
    def setup_method(self):
        self.fe = FeatureEngineer()

    def _compute(self, signals, members, committee_size=5):
        return self.fe.compute(
            "acct-1", "acme.com", signals, members, committee_size, as_of=_NOW
        )

    def test_unique_members_7d(self):
        m = [
            _make_member(1.0, member_id="m1"),
            _make_member(2.0, member_id="m2"),
            _make_member(8.0, member_id="m3"),  # outside 7d
        ]
        fv = self._compute([], m)
        assert fv.unique_members_7d == 2

    def test_unique_members_30d(self):
        m = [
            _make_member(5.0,  member_id="m1"),
            _make_member(20.0, member_id="m2"),
            _make_member(31.0, member_id="m3"),  # outside 30d
        ]
        fv = self._compute([], m)
        assert fv.unique_members_30d == 2

    def test_channel_count_7d(self):
        s = [
            _make_signal(2.0, source_system="WEB"),
            _make_signal(3.0, source_system="EMAIL"),
            _make_signal(4.0, source_system="EMAIL"),   # duplicate channel
            _make_signal(10.0, source_system="CRM"),    # outside 7d
        ]
        fv = self._compute(s, [])
        assert fv.channel_count_7d == 2

    def test_role_weighted_score_7d(self):
        m = [
            _make_member(1.0, weighted_score=0.6),
            _make_member(3.0, weighted_score=1.2),
            _make_member(10.0, weighted_score=99.0),  # outside 7d
        ]
        fv = self._compute([], m)
        assert fv.role_weighted_score_7d == pytest.approx(1.8)

    def test_c_suite_vp_signals_7d(self):
        m = [
            _make_member(1.0, seniority_level="C_SUITE", signal_count=5),
            _make_member(2.0, seniority_level="VP",       signal_count=3),
            _make_member(3.0, seniority_level="DIRECTOR", signal_count=2),  # not senior
            _make_member(10.0, seniority_level="C_SUITE", signal_count=9),  # outside 7d
        ]
        fv = self._compute([], m)
        assert fv.c_suite_vp_signals_7d == 8

    def test_committee_coverage_capped_at_1(self):
        # 3 unique members / committee_size 2 → would be 1.5 without cap
        m = [
            _make_member(1.0, member_id="m1"),
            _make_member(2.0, member_id="m2"),
            _make_member(3.0, member_id="m3"),
        ]
        fv = self._compute([], m, committee_size=2)
        assert fv.committee_coverage_pct_30d == 1.0

    def test_committee_coverage_zero_size(self):
        m = [_make_member(1.0)]
        fv = self._compute([], m, committee_size=0)
        assert fv.committee_coverage_pct_30d == 0.0


# ---------------------------------------------------------------------------
# FeatureEngineer.compute — velocity
# ---------------------------------------------------------------------------


class TestFeatureEngineerVelocity:
    def setup_method(self):
        self.fe = FeatureEngineer()

    def _compute(self, signals):
        return self.fe.compute("acct-1", "acme.com", signals, [], 1, as_of=_NOW)

    def test_velocity_zero_when_no_signals(self):
        fv = self._compute([])
        assert fv.velocity_7d == 0.0

    def test_positive_velocity(self):
        # Current window: 20 signals; prior 7d window: 10 signals
        current = _make_signal(3.0, signal_count=20)   # within 7d
        prior   = _make_signal(10.0, signal_count=10)  # 7d–14d ago
        fv = self._compute([current, prior])
        assert fv.velocity_7d == pytest.approx(1.0)

    def test_negative_velocity(self):
        current = _make_signal(3.0, signal_count=5)
        prior   = _make_signal(10.0, signal_count=10)
        fv = self._compute([current, prior])
        assert fv.velocity_7d == pytest.approx(-0.5)


# ---------------------------------------------------------------------------
# FeatureEngineer.compute — days_since_last_signal
# ---------------------------------------------------------------------------


class TestDaysSinceLastSignal:
    def setup_method(self):
        self.fe = FeatureEngineer()

    def _compute(self, signals):
        return self.fe.compute("a", "b.com", signals, [], 1, as_of=_NOW)

    def test_no_signals_returns_999(self):
        fv = self._compute([])
        assert fv.days_since_last_signal == 999.0

    def test_signal_today_returns_approx_zero(self):
        fv = self._compute([_make_signal(0.0)])
        assert fv.days_since_last_signal < 0.01

    def test_picks_most_recent_signal(self):
        fv = self._compute([_make_signal(10.0), _make_signal(3.0)])
        assert fv.days_since_last_signal == pytest.approx(3.0, abs=0.01)

    def test_zero_count_signal_excluded(self):
        # A row with signal_count=0 should not update last-signal
        old = SignalRow(
            signal_date=_NOW - timedelta(days=1),
            source_system="WEB",
            signal_count=0,
        )
        fv = self._compute([old])
        assert fv.days_since_last_signal == 999.0


# ---------------------------------------------------------------------------
# FeatureEngineer.compute — to_feature_array ordering
# ---------------------------------------------------------------------------


class TestToFeatureArray:
    def test_length_matches_feature_names(self):
        from scoring.models import FEATURE_NAMES

        fe = FeatureEngineer()
        fv = fe.compute("a", "b.com", [], [], 1, as_of=_NOW)
        arr = fv.to_feature_array()
        assert len(arr) == len(FEATURE_NAMES)

    def test_all_values_are_floats(self):
        fe = FeatureEngineer()
        fv = fe.compute("a", "b.com", [], [], 1, as_of=_NOW)
        for v in fv.to_feature_array():
            assert isinstance(v, float)
