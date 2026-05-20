"""Tests for scoring.evaluation.harness — EvaluationHarness and EvaluationResult."""

from __future__ import annotations

import numpy as np
import pytest
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from scoring.evaluation.harness import EvaluationHarness, EvaluationResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_perfect_model() -> Pipeline:
    """A pipeline that memorises perfectly separable data."""
    X_train = np.array([[0.0], [1.0], [2.0], [3.0]])
    y_train = np.array([0, 0, 1, 1])
    pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("clf", LogisticRegression(C=100, random_state=0)),
    ])
    pipeline.fit(X_train, y_train)
    return pipeline


def _make_random_model(random_state: int = 42) -> Pipeline:
    """A pipeline trained on noise — expected ~0.5 AUC."""
    rng = np.random.default_rng(random_state)
    X_train = rng.normal(size=(200, 4))
    y_train = rng.integers(0, 2, size=200)
    pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("clf", LogisticRegression(random_state=0)),
    ])
    pipeline.fit(X_train, y_train)
    return pipeline


def _perfectly_separable_test_data() -> tuple[np.ndarray, np.ndarray]:
    X = np.array([[0.0], [0.5], [2.5], [3.0]])
    y = np.array([0, 0, 1, 1])
    return X, y


def _noisy_test_data(n: int = 100, random_state: int = 0) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(random_state)
    X = rng.normal(size=(n, 4))
    y = rng.integers(0, 2, size=n)
    return X, y


# ---------------------------------------------------------------------------
# EvaluationResult
# ---------------------------------------------------------------------------


class TestEvaluationResult:
    def _make_result(self, auc: float = 0.80, **kwargs) -> EvaluationResult:
        defaults = dict(
            model_name="TestModel",
            n_samples=100,
            n_positive=50,
            n_negative=50,
            accuracy=0.80,
            precision=0.78,
            recall=0.82,
            f1_score=0.80,
            auc_roc=auc,
            confusion_matrix=[[40, 10], [8, 42]],
        )
        defaults.update(kwargs)
        return EvaluationResult(**defaults)

    def test_passes_auc_threshold_above(self):
        assert self._make_result(auc=0.75).passes_auc_threshold is True

    def test_passes_auc_threshold_exactly(self):
        assert self._make_result(auc=0.70).passes_auc_threshold is True

    def test_passes_auc_threshold_below(self):
        assert self._make_result(auc=0.69).passes_auc_threshold is False

    def test_summary_contains_pass(self):
        text = self._make_result(auc=0.80).summary()
        assert "PASS" in text
        assert "AUC-ROC" in text

    def test_summary_contains_fail(self):
        text = self._make_result(auc=0.60).summary()
        assert "FAIL" in text

    def test_summary_contains_confusion_matrix_labels(self):
        text = self._make_result().summary()
        assert "TN=" in text
        assert "FP=" in text
        assert "FN=" in text
        assert "TP=" in text

    def test_summary_contains_model_name(self):
        text = self._make_result(model_name="MyModel v2").summary()
        assert "MyModel v2" in text

    def test_threshold_analysis_defaults_empty(self):
        r = self._make_result()
        assert r.threshold_analysis == []


# ---------------------------------------------------------------------------
# EvaluationHarness.evaluate — metrics
# ---------------------------------------------------------------------------


class TestEvaluationHarnessMetrics:
    def setup_method(self):
        self.harness = EvaluationHarness(model_name="TestModel")

    def test_returns_evaluation_result(self):
        model = _make_perfect_model()
        X, y = _perfectly_separable_test_data()
        result = self.harness.evaluate(model, X, y)
        assert isinstance(result, EvaluationResult)

    def test_perfect_model_high_auc(self):
        model = _make_perfect_model()
        X, y = _perfectly_separable_test_data()
        result = self.harness.evaluate(model, X, y)
        assert result.auc_roc >= 0.95

    def test_n_samples_correct(self):
        model = _make_random_model()
        X, y = _noisy_test_data(n=80)
        result = self.harness.evaluate(model, X, y)
        assert result.n_samples == 80

    def test_n_positive_and_negative_sum_to_n_samples(self):
        model = _make_random_model()
        X, y = _noisy_test_data(n=100)
        result = self.harness.evaluate(model, X, y)
        assert result.n_positive + result.n_negative == result.n_samples

    def test_accuracy_in_range(self):
        model = _make_random_model()
        X, y = _noisy_test_data(n=100)
        result = self.harness.evaluate(model, X, y)
        assert 0.0 <= result.accuracy <= 1.0

    def test_auc_roc_in_range(self):
        model = _make_random_model()
        X, y = _noisy_test_data(n=100)
        result = self.harness.evaluate(model, X, y)
        assert 0.0 <= result.auc_roc <= 1.0

    def test_confusion_matrix_shape(self):
        model = _make_random_model()
        X, y = _noisy_test_data(n=100)
        result = self.harness.evaluate(model, X, y)
        cm = result.confusion_matrix
        assert len(cm) == 2
        assert len(cm[0]) == 2
        assert len(cm[1]) == 2

    def test_model_name_propagated(self):
        harness = EvaluationHarness(model_name="MyClassifier v3")
        model = _make_random_model()
        X, y = _noisy_test_data()
        result = harness.evaluate(model, X, y)
        assert result.model_name == "MyClassifier v3"


# ---------------------------------------------------------------------------
# EvaluationHarness — threshold analysis
# ---------------------------------------------------------------------------


class TestThresholdAnalysis:
    def test_threshold_analysis_length(self):
        harness = EvaluationHarness(n_threshold_steps=5)
        model = _make_perfect_model()
        X, y = _perfectly_separable_test_data()
        result = harness.evaluate(model, X, y)
        assert len(result.threshold_analysis) == 5

    def test_threshold_analysis_keys(self):
        harness = EvaluationHarness(n_threshold_steps=3)
        model = _make_random_model()
        X, y = _noisy_test_data(n=100)
        result = harness.evaluate(model, X, y)
        for entry in result.threshold_analysis:
            assert "threshold" in entry
            assert "precision" in entry
            assert "recall" in entry
            assert "f1" in entry

    def test_thresholds_in_range(self):
        harness = EvaluationHarness(n_threshold_steps=10)
        model = _make_random_model()
        X, y = _noisy_test_data(n=100)
        result = harness.evaluate(model, X, y)
        for entry in result.threshold_analysis:
            assert 0.0 <= entry["threshold"] <= 1.0
            assert 0.0 <= entry["precision"] <= 1.0
            assert 0.0 <= entry["recall"] <= 1.0
            assert 0.0 <= entry["f1"] <= 1.0


# ---------------------------------------------------------------------------
# EvaluationHarness.report
# ---------------------------------------------------------------------------


class TestReport:
    def test_report_is_string(self):
        harness = EvaluationHarness()
        model = _make_perfect_model()
        X, y = _perfectly_separable_test_data()
        result = harness.evaluate(model, X, y)
        assert isinstance(harness.report(result), str)

    def test_report_includes_threshold_section(self):
        harness = EvaluationHarness(n_threshold_steps=3)
        model = _make_perfect_model()
        X, y = _perfectly_separable_test_data()
        result = harness.evaluate(model, X, y)
        report = harness.report(result)
        assert "Threshold analysis" in report

    def test_report_no_threshold_section_when_empty(self):
        harness = EvaluationHarness()
        model = _make_random_model()
        X, y = _noisy_test_data()
        result = harness.evaluate(model, X, y)
        # Override threshold_analysis to be empty
        result.threshold_analysis = []
        report = harness.report(result)
        assert "Threshold analysis" not in report
