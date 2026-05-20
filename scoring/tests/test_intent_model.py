"""Tests for scoring.intent.model — IntentNetworkModel."""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone

import numpy as np
import pytest

from scoring.intent.model import IntentNetworkModel
from scoring.intent.train import generate_synthetic_data
from scoring.models import AccountFeatureVector, FEATURE_NAMES, IntentScore

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def trained_model() -> IntentNetworkModel:
    X, y = generate_synthetic_data(n_samples=500, random_state=0)
    from sklearn.model_selection import train_test_split
    X_train, _, y_train, _ = train_test_split(X, y, test_size=0.2, random_state=0, stratify=y)
    return IntentNetworkModel.from_training_run(X_train, y_train)


def _make_fv(**kwargs) -> AccountFeatureVector:
    defaults = {
        "account_id": "test-acct",
        "account_domain": "example.com",
        "as_of": datetime(2024, 6, 1, tzinfo=timezone.utc),
    }
    defaults.update(kwargs)
    return AccountFeatureVector(**defaults)


# ---------------------------------------------------------------------------
# from_training_run
# ---------------------------------------------------------------------------


class TestFromTrainingRun:
    def test_returns_instance(self):
        X, y = generate_synthetic_data(n_samples=200, random_state=1)
        model = IntentNetworkModel.from_training_run(X, y)
        assert isinstance(model, IntentNetworkModel)

    def test_pipeline_is_fitted(self):
        X, y = generate_synthetic_data(n_samples=200, random_state=2)
        model = IntentNetworkModel.from_training_run(X, y)
        assert model._pipeline is not None

    def test_model_version_constant(self):
        assert IntentNetworkModel.MODEL_VERSION == "1.0.0"


# ---------------------------------------------------------------------------
# _require_fitted guard
# ---------------------------------------------------------------------------


class TestRequireFitted:
    def test_unfitted_predict_raises(self):
        model = IntentNetworkModel()
        fv = _make_fv()
        with pytest.raises(RuntimeError, match="not fitted"):
            model.predict(fv)

    def test_unfitted_predict_batch_raises(self):
        model = IntentNetworkModel()
        with pytest.raises(RuntimeError, match="not fitted"):
            model.predict_batch([_make_fv()])


# ---------------------------------------------------------------------------
# predict — output contract
# ---------------------------------------------------------------------------


class TestPredict:
    def test_returns_intent_score(self, trained_model):
        fv = _make_fv(total_signals_7d=10, high_intent_signals_7d=3)
        result = trained_model.predict(fv)
        assert isinstance(result, IntentScore)

    def test_score_in_range(self, trained_model):
        fv = _make_fv()
        result = trained_model.predict(fv)
        assert 0.0 <= result.score <= 100.0

    def test_confidence_in_range(self, trained_model):
        fv = _make_fv()
        result = trained_model.predict(fv)
        assert 0.0 <= result.confidence <= 1.0

    def test_account_id_propagated(self, trained_model):
        fv = _make_fv(account_id="xyz-789", account_domain="acme.com")
        result = trained_model.predict(fv)
        assert result.account_id == "xyz-789"
        assert result.account_domain == "acme.com"

    def test_model_version_propagated(self, trained_model):
        fv = _make_fv()
        result = trained_model.predict(fv)
        assert result.model_version == IntentNetworkModel.MODEL_VERSION

    def test_high_intent_fv_scores_higher(self, trained_model):
        high = _make_fv(
            total_signals_7d=50,
            high_intent_signals_7d=20,
            c_suite_vp_signals_7d=5,
            negative_signals_7d=0,
            velocity_7d=2.0,
        )
        low = _make_fv(
            total_signals_7d=2,
            high_intent_signals_7d=0,
            negative_signals_7d=5,
            velocity_7d=-0.5,
            days_since_last_signal=30.0,
        )
        assert trained_model.predict(high).score > trained_model.predict(low).score

    def test_is_high_intent_threshold(self, trained_model):
        fv = _make_fv(
            total_signals_7d=60,
            strong_signals_7d=30,
            high_intent_signals_7d=25,
            c_suite_vp_signals_7d=6,
            negative_signals_7d=0,
            velocity_7d=3.0,
            channel_count_7d=4,
        )
        result = trained_model.predict(fv)
        # Strong signal account should flag as high intent
        if result.score >= 70.0:
            assert result.is_high_intent
        else:
            assert not result.is_high_intent


# ---------------------------------------------------------------------------
# predict_batch
# ---------------------------------------------------------------------------


class TestPredictBatch:
    def test_empty_batch_returns_empty(self, trained_model):
        assert trained_model.predict_batch([]) == []

    def test_batch_length_matches_input(self, trained_model):
        fvs = [_make_fv(account_id=f"a{i}") for i in range(5)]
        results = trained_model.predict_batch(fvs)
        assert len(results) == 5

    def test_batch_matches_single_predictions(self, trained_model):
        fvs = [
            _make_fv(account_id="a1", total_signals_7d=10),
            _make_fv(account_id="a2", total_signals_7d=30, high_intent_signals_7d=10),
        ]
        batch_results = trained_model.predict_batch(fvs)
        single_results = [trained_model.predict(fv) for fv in fvs]
        for br, sr in zip(batch_results, single_results):
            assert br.score == pytest.approx(sr.score, abs=0.001)

    def test_batch_preserves_order(self, trained_model):
        ids = [f"account-{i}" for i in range(10)]
        fvs = [_make_fv(account_id=aid) for aid in ids]
        results = trained_model.predict_batch(fvs)
        assert [r.account_id for r in results] == ids


# ---------------------------------------------------------------------------
# save / load roundtrip
# ---------------------------------------------------------------------------


class TestSaveLoad:
    def test_save_and_load_produces_same_score(self, trained_model):
        fv = _make_fv(total_signals_7d=15, high_intent_signals_7d=5)
        original_score = trained_model.predict(fv).score

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "intent_model.joblib")
            trained_model.save(path)

            loaded = IntentNetworkModel()
            loaded.load(path)
            loaded_score = loaded.predict(fv).score

        assert loaded_score == pytest.approx(original_score, abs=0.001)

    def test_load_missing_file_raises(self):
        model = IntentNetworkModel()
        with pytest.raises(FileNotFoundError):
            model.load("/nonexistent/path/model.joblib")


# ---------------------------------------------------------------------------
# AUC-ROC gate (integration)
# ---------------------------------------------------------------------------


class TestAucRocGate:
    def test_auc_roc_above_threshold_on_synthetic_data(self):
        from sklearn.metrics import roc_auc_score
        from sklearn.model_selection import train_test_split

        X, y = generate_synthetic_data(n_samples=2000, random_state=42)
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.20, random_state=42, stratify=y
        )
        model = IntentNetworkModel.from_training_run(X_train, y_train)
        y_prob = model._pipeline.predict_proba(X_test)[:, 1]
        auc = roc_auc_score(y_test, y_prob)
        assert auc >= 0.70, f"AUC-ROC {auc:.4f} below 0.70 threshold"
