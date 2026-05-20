"""Tests for scoring.fatigue.engine — FatigueScoreEngine composite scorer."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from scoring.fatigue.engine import (
    FatigueScoreEngine,
    _classify_severity,
    _DEFAULT_WEIGHTS,
    _SEGMENT_WEIGHTS,
)
from scoring.models import (
    AccountFatigueScore,
    FatigueComponent,
    FatigueSeverity,
    OutreachDaySummary,
)

_NOW = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row(
    days_ago: float,
    member_id: str = "m1",
    *,
    sent: int = 1,
    opened: int = 0,
    replied: int = 0,
    meaningful_reply: int = 0,
    bounced: int = 0,
    unsubscribed: int = 0,
    spam: int = 0,
) -> OutreachDaySummary:
    return OutreachDaySummary(
        sent_date=_NOW - timedelta(days=days_ago),
        member_id=member_id,
        channel="EMAIL",
        sent_count=sent,
        opened_count=opened,
        replied_count=replied,
        meaningful_reply_count=meaningful_reply,
        bounced_count=bounced,
        unsubscribed_count=unsubscribed,
        spam_reported_count=spam,
    )


def _make_high_fatigue_rows() -> list[OutreachDaySummary]:
    """Rows representing an over-contacted, disengaged account."""
    rows = []
    for i in range(30):
        rows.append(_row(i, sent=4, opened=0, unsubscribed=1 if i == 5 else 0, spam=1 if i == 10 else 0))
    return rows


def _make_healthy_rows() -> list[OutreachDaySummary]:
    """Rows representing a well-engaged, normally-contacted account."""
    rows = []
    for i in range(14):
        rows.append(_row(i, sent=1, opened=1, replied=1 if i == 2 else 0, meaningful_reply=1 if i == 2 else 0))
    return rows


# ===========================================================================
# _classify_severity
# ===========================================================================


class TestClassifySeverity:
    @pytest.mark.parametrize("score,expected", [
        (0.0,  FatigueSeverity.LOW),
        (29.9, FatigueSeverity.LOW),
        (30.0, FatigueSeverity.MEDIUM),
        (59.9, FatigueSeverity.MEDIUM),
        (60.0, FatigueSeverity.HIGH),
        (79.9, FatigueSeverity.HIGH),
        (80.0, FatigueSeverity.CRITICAL),
        (100.0, FatigueSeverity.CRITICAL),
    ])
    def test_severity_thresholds(self, score, expected):
        assert _classify_severity(score) == expected


# ===========================================================================
# FatigueScoreEngine.compute — output contract
# ===========================================================================


class TestFatigueScoreEngineContract:
    def setup_method(self):
        self.engine = FatigueScoreEngine()

    def test_returns_account_fatigue_score(self):
        result = self.engine.compute("a", "b.com", [], as_of=_NOW)
        assert isinstance(result, AccountFatigueScore)

    def test_account_id_propagated(self):
        result = self.engine.compute("my-acct-id", "example.com", [], as_of=_NOW)
        assert result.account_id == "my-acct-id"

    def test_domain_propagated(self):
        result = self.engine.compute("a", "acme.com", [], as_of=_NOW)
        assert result.account_domain == "acme.com"

    def test_score_in_range(self):
        rows = _make_high_fatigue_rows()
        result = self.engine.compute("a", "b.com", rows, as_of=_NOW)
        assert 0.0 <= result.score <= 100.0

    def test_score_zero_for_empty_rows(self):
        result = self.engine.compute("a", "b.com", [], as_of=_NOW)
        assert result.score == 0.0

    def test_severity_low_for_empty_rows(self):
        result = self.engine.compute("a", "b.com", [], as_of=_NOW)
        assert result.severity == FatigueSeverity.LOW

    def test_exactly_five_components(self):
        result = self.engine.compute("a", "b.com", [], as_of=_NOW)
        assert len(result.components) == 5

    def test_component_names_correct(self):
        result = self.engine.compute("a", "b.com", [], as_of=_NOW)
        names = {c.name for c in result.components}
        assert names == {
            "outreach_frequency",
            "engagement_decay",
            "negative_signal",
            "contact_concentration",
            "recency",
        }

    def test_component_scores_in_range(self):
        rows = _make_high_fatigue_rows()
        result = self.engine.compute("a", "b.com", rows, as_of=_NOW)
        for c in result.components:
            assert 0.0 <= c.score <= 100.0

    def test_component_weights_sum_to_one(self):
        result = self.engine.compute("a", "b.com", [], as_of=_NOW)
        total = sum(c.weight for c in result.components)
        assert total == pytest.approx(1.0, abs=0.001)

    def test_account_segment_stored(self):
        result = self.engine.compute("a", "b.com", [], account_segment="ENTERPRISE", as_of=_NOW)
        assert result.account_segment == "ENTERPRISE"

    def test_computed_at_matches_as_of(self):
        result = self.engine.compute("a", "b.com", [], as_of=_NOW)
        assert result.computed_at == _NOW


# ===========================================================================
# FatigueScoreEngine — composite score correctness
# ===========================================================================


class TestCompositeScore:
    def setup_method(self):
        self.engine = FatigueScoreEngine()

    def test_composite_is_weighted_sum_of_components(self):
        rows = _make_high_fatigue_rows()
        result = self.engine.compute("a", "b.com", rows, as_of=_NOW)
        expected = sum(c.weighted_score for c in result.components)
        assert result.score == pytest.approx(expected, abs=0.01)

    def test_high_fatigue_rows_score_higher_than_healthy(self):
        high = self.engine.compute("a", "b.com", _make_high_fatigue_rows(), as_of=_NOW)
        healthy = self.engine.compute("a", "b.com", _make_healthy_rows(), as_of=_NOW)
        assert high.score > healthy.score

    def test_high_fatigue_rows_trigger_threshold(self):
        result = self.engine.compute("a", "b.com", _make_high_fatigue_rows(), as_of=_NOW)
        assert result.is_over_threshold  # HIGH or CRITICAL

    def test_healthy_rows_do_not_trigger_threshold(self):
        result = self.engine.compute("a", "b.com", _make_healthy_rows(), as_of=_NOW)
        assert not result.is_over_threshold  # LOW or MEDIUM

    def test_score_clamped_to_100(self):
        # Even pathological input cannot push score above 100
        engine = FatigueScoreEngine(weights_override={
            "outreach_frequency": 1.0,
            "negative_signal": 1.0,
            "engagement_decay": 1.0,
            "contact_concentration": 1.0,
            "recency": 1.0,
        })
        rows = _make_high_fatigue_rows()
        result = engine.compute("a", "b.com", rows, as_of=_NOW)
        assert result.score <= 100.0

    def test_score_clamped_to_zero(self):
        result = self.engine.compute("a", "b.com", [], as_of=_NOW)
        assert result.score >= 0.0


# ===========================================================================
# FatigueScoreEngine — segment weight selection
# ===========================================================================


class TestSegmentWeights:
    def test_enterprise_weights_applied(self):
        result = FatigueScoreEngine().compute(
            "a", "b.com", [], account_segment="ENTERPRISE", as_of=_NOW
        )
        ent_weights = _SEGMENT_WEIGHTS["ENTERPRISE"]
        for component in result.components:
            assert component.weight == pytest.approx(
                ent_weights[component.name], abs=0.001
            )

    def test_smb_weights_applied(self):
        result = FatigueScoreEngine().compute(
            "a", "b.com", [], account_segment="SMB", as_of=_NOW
        )
        smb_weights = _SEGMENT_WEIGHTS["SMB"]
        for component in result.components:
            assert component.weight == pytest.approx(
                smb_weights[component.name], abs=0.001
            )

    def test_unknown_segment_falls_back_to_default(self):
        result = FatigueScoreEngine().compute(
            "a", "b.com", [], account_segment="STARTUP", as_of=_NOW
        )
        for component in result.components:
            assert component.weight == pytest.approx(
                _DEFAULT_WEIGHTS[component.name], abs=0.001
            )

    def test_weights_override_ignores_segment(self):
        custom = {
            "outreach_frequency": 0.5,
            "negative_signal": 0.5,
            "engagement_decay": 0.0,
            "contact_concentration": 0.0,
            "recency": 0.0,
        }
        engine = FatigueScoreEngine(weights_override=custom)
        result = engine.compute("a", "b.com", [], account_segment="ENTERPRISE", as_of=_NOW)
        freq_comp = result.component_by_name("outreach_frequency")
        assert freq_comp is not None
        assert freq_comp.weight == pytest.approx(0.5)

    def test_enterprise_more_sensitive_to_frequency_than_smb(self):
        # Same outreach volume should produce higher fatigue for Enterprise
        rows = [_row(i, sent=5) for i in range(7)]
        ent = FatigueScoreEngine().compute("a", "b.com", rows, account_segment="ENTERPRISE", as_of=_NOW)
        smb = FatigueScoreEngine().compute("a", "b.com", rows, account_segment="SMB", as_of=_NOW)
        # Enterprise has lower baseline frequency, so same sends = higher frequency ratio
        ent_freq = ent.component_by_name("outreach_frequency")
        smb_freq = smb.component_by_name("outreach_frequency")
        assert ent_freq is not None and smb_freq is not None
        assert ent_freq.score > smb_freq.score


# ===========================================================================
# AccountFatigueScore helpers
# ===========================================================================


class TestAccountFatigueScoreHelpers:
    def _make(self, score: float) -> AccountFatigueScore:
        from scoring.fatigue.engine import _classify_severity
        return AccountFatigueScore(
            account_id="a",
            account_domain="b.com",
            score=score,
            severity=_classify_severity(score),
        )

    def test_is_over_threshold_true_for_high(self):
        assert self._make(65.0).is_over_threshold is True

    def test_is_over_threshold_true_for_critical(self):
        assert self._make(85.0).is_over_threshold is True

    def test_is_over_threshold_false_for_medium(self):
        assert self._make(45.0).is_over_threshold is False

    def test_is_over_threshold_false_for_low(self):
        assert self._make(10.0).is_over_threshold is False

    def test_invalid_score_raises(self):
        with pytest.raises(ValueError):
            AccountFatigueScore(
                account_id="a", account_domain="b.com",
                score=101.0, severity=FatigueSeverity.CRITICAL,
            )

    def test_to_dict_roundtrip(self):
        engine = FatigueScoreEngine()
        score = engine.compute("a", "b.com", [], as_of=_NOW)
        d = score.to_dict()
        assert d["account_id"] == "a"
        assert d["account_domain"] == "b.com"
        assert isinstance(d["score"], float)
        assert isinstance(d["components"], list)
        assert len(d["components"]) == 5

    def test_component_by_name_returns_correct(self):
        engine = FatigueScoreEngine()
        score = engine.compute("a", "b.com", [], as_of=_NOW)
        comp = score.component_by_name("recency")
        assert comp is not None
        assert comp.name == "recency"

    def test_component_by_name_returns_none_for_unknown(self):
        engine = FatigueScoreEngine()
        score = engine.compute("a", "b.com", [], as_of=_NOW)
        assert score.component_by_name("nonexistent") is None
