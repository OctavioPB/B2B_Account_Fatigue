"""Tests for scoring.churn.model — ChurnPredictor."""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone

import pytest

from scoring.churn.model import ChurnPredictor, _classify_risk
from scoring.churn.train import generate_synthetic_churn_data
from scoring.models import AccountFeatureVector, ChurnPrediction, ChurnRiskLevel

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def trained_predictor() -> ChurnPredictor:
    X, y = generate_synthetic_churn_data(n_samples=500, random_state=0)
    from sklearn.model_selection import train_test_split
    X_train, _, y_train, _ = train_test_split(X, y, test_size=0.2, random_state=0, stratify=y)
    return ChurnPredictor.from_training_run(X_train, y_train)


def _make_fv(**kwargs) -> AccountFeatureVector:
    defaults = {
        "account_id": "test-acct",
        "account_domain": "example.com",
        "as_of": datetime(2024, 6, 1, tzinfo=timezone.utc),
    }
    defaults.update(kwargs)
    return AccountFeatureVector(**defaults)


# ---------------------------------------------------------------------------
# _classify_risk thresholds
# ---------------------------------------------------------------------------


class TestClassifyRisk:
    @pytest.mark.parametrize("prob,expected", [
        (0.00, ChurnRiskLevel.LOW),
        (0.19, ChurnRiskLevel.LOW),
        (0.20, ChurnRiskLevel.MEDIUM),
        (0.49, ChurnRiskLevel.MEDIUM),
        (0.50, ChurnRiskLevel.HIGH),
        (0.74, ChurnRiskLevel.HIGH),
        (0.75, ChurnRiskLevel.CRITICAL),
        (1.00, ChurnRiskLevel.CRITICAL),
    ])
    def test_risk_tier(self, prob, expected):
        assert _classify_risk(prob) == expected


# ---------------------------------------------------------------------------
# from_training_run
# ---------------------------------------------------------------------------


class TestFromTrainingRun:
    def test_returns_instance(self):
        X, y = generate_synthetic_churn_data(n_samples=200, random_state=1)
        predictor = ChurnPredictor.from_training_run(X, y)
        assert isinstance(predictor, ChurnPredictor)

    def test_pipeline_is_fitted(self):
        X, y = generate_synthetic_churn_data(n_samples=200, random_state=2)
        predictor = ChurnPredictor.from_training_run(X, y)
        assert predictor._pipeline is not None

    def test_model_version_constant(self):
        assert ChurnPredictor.MODEL_VERSION == "1.0.0"


# ---------------------------------------------------------------------------
# _require_fitted guard
# ---------------------------------------------------------------------------


class TestRequireFitted:
    def test_unfitted_predict_raises(self):
        predictor = ChurnPredictor()
        with pytest.raises(RuntimeError, match="not fitted"):
            predictor.predict(_make_fv())

    def test_unfitted_batch_raises(self):
        predictor = ChurnPredictor()
        with pytest.raises(RuntimeError, match="not fitted"):
            predictor.predict_batch([_make_fv()])


# ---------------------------------------------------------------------------
# predict — output contract
# ---------------------------------------------------------------------------


class TestPredict:
    def test_returns_churn_prediction(self, trained_predictor):
        result = trained_predictor.predict(_make_fv())
        assert isinstance(result, ChurnPrediction)

    def test_probability_in_range(self, trained_predictor):
        result = trained_predictor.predict(_make_fv())
        assert 0.0 <= result.churn_probability <= 1.0

    def test_risk_level_is_valid_enum(self, trained_predictor):
        result = trained_predictor.predict(_make_fv())
        assert isinstance(result.risk_level, ChurnRiskLevel)

    def test_risk_level_consistent_with_probability(self, trained_predictor):
        fv = _make_fv()
        result = trained_predictor.predict(fv)
        expected_level = _classify_risk(result.churn_probability)
        assert result.risk_level == expected_level

    def test_account_id_propagated(self, trained_predictor):
        fv = _make_fv(account_id="churn-test-789")
        result = trained_predictor.predict(fv)
        assert result.account_id == "churn-test-789"

    def test_model_version_propagated(self, trained_predictor):
        result = trained_predictor.predict(_make_fv())
        assert result.model_version == ChurnPredictor.MODEL_VERSION

    def test_high_churn_fv_scores_higher(self, trained_predictor):
        churning = _make_fv(
            negative_signals_7d=7,
            velocity_7d=-0.9,
            days_since_last_signal=25.0,
            high_intent_signals_7d=0,
            committee_coverage_pct_30d=0.1,
        )
        healthy = _make_fv(
            negative_signals_7d=0,
            velocity_7d=2.0,
            days_since_last_signal=1.0,
            high_intent_signals_7d=10,
            committee_coverage_pct_30d=0.8,
        )
        assert (
            trained_predictor.predict(churning).churn_probability
            > trained_predictor.predict(healthy).churn_probability
        )

    def test_signal_breakdown_populated(self, trained_predictor):
        result = trained_predictor.predict(_make_fv())
        assert "churn_probability" in result.signal_breakdown
        assert "days_since_last_signal" in result.signal_breakdown
        assert "risk_level" in result.signal_breakdown

    def test_is_high_risk_true_for_high_and_critical(self, trained_predictor):
        fv = _make_fv()
        result = trained_predictor.predict(fv)
        expected = result.risk_level in (ChurnRiskLevel.HIGH, ChurnRiskLevel.CRITICAL)
        assert result.is_high_risk == expected


# ---------------------------------------------------------------------------
# predict_batch
# ---------------------------------------------------------------------------


class TestPredictBatch:
    def test_empty_batch_returns_empty(self, trained_predictor):
        assert trained_predictor.predict_batch([]) == []

    def test_batch_length_matches_input(self, trained_predictor):
        fvs = [_make_fv(account_id=f"a{i}") for i in range(4)]
        results = trained_predictor.predict_batch(fvs)
        assert len(results) == 4

    def test_batch_matches_single_predictions(self, trained_predictor):
        fvs = [
            _make_fv(account_id="a1", negative_signals_7d=3, velocity_7d=-0.5),
            _make_fv(account_id="a2", negative_signals_7d=0, velocity_7d=1.0),
        ]
        batch = trained_predictor.predict_batch(fvs)
        singles = [trained_predictor.predict(fv) for fv in fvs]
        for br, sr in zip(batch, singles):
            assert br.churn_probability == pytest.approx(sr.churn_probability, abs=0.001)

    def test_batch_preserves_order(self, trained_predictor):
        ids = [f"acct-{i}" for i in range(8)]
        fvs = [_make_fv(account_id=aid) for aid in ids]
        results = trained_predictor.predict_batch(fvs)
        assert [r.account_id for r in results] == ids


# ---------------------------------------------------------------------------
# save / load roundtrip
# ---------------------------------------------------------------------------


class TestSaveLoad:
    def test_save_load_produces_same_probability(self, trained_predictor):
        fv = _make_fv(negative_signals_7d=4, days_since_last_signal=15.0)
        original_prob = trained_predictor.predict(fv).churn_probability

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "churn_model.joblib")
            trained_predictor.save(path)

            loaded = ChurnPredictor()
            loaded.load(path)
            loaded_prob = loaded.predict(fv).churn_probability

        assert loaded_prob == pytest.approx(original_prob, abs=0.001)

    def test_load_missing_file_raises(self):
        predictor = ChurnPredictor()
        with pytest.raises(FileNotFoundError):
            predictor.load("/nonexistent/churn_model.joblib")


# ---------------------------------------------------------------------------
# AUC-ROC gate (integration)
# ---------------------------------------------------------------------------


class TestAucRocGate:
    def test_auc_roc_above_threshold_on_synthetic_data(self):
        from sklearn.metrics import roc_auc_score
        from sklearn.model_selection import train_test_split

        X, y = generate_synthetic_churn_data(n_samples=2000, random_state=42)
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.20, random_state=42, stratify=y
        )
        predictor = ChurnPredictor.from_training_run(X_train, y_train)
        y_prob = predictor._pipeline.predict_proba(X_test)[:, 1]
        auc = roc_auc_score(y_test, y_prob)
        assert auc >= 0.70, f"AUC-ROC {auc:.4f} below 0.70 threshold"
