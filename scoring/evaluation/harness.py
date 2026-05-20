"""Offline evaluation harness for Intent Network Model and Churn Predictor.

EvaluationHarness.evaluate() accepts any fitted sklearn-compatible model
and a held-out test set, then returns a structured EvaluationResult with:
  - accuracy, precision, recall, F1
  - AUC-ROC (primary DoD metric — must be ≥ 0.70)
  - confusion matrix
  - per-threshold operating points

Usage::

    from scoring.evaluation.harness import EvaluationHarness, EvaluationResult

    harness = EvaluationHarness(model_name="IntentNetworkModel v1.0.0")
    result = harness.evaluate(model, X_test, y_test)
    print(harness.report(result))
    assert result.auc_roc >= 0.70, f"AUC-ROC {result.auc_roc:.3f} below threshold"
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocol for duck-typed sklearn-compatible models
# ---------------------------------------------------------------------------


class ScoringModel(Protocol):
    """Minimal sklearn-compatible model interface."""

    def predict(self, X: "np.ndarray") -> "np.ndarray": ...
    def predict_proba(self, X: "np.ndarray") -> "np.ndarray": ...


# ---------------------------------------------------------------------------
# Evaluation result
# ---------------------------------------------------------------------------


@dataclass
class EvaluationResult:
    """Structured evaluation metrics for one model on one test split."""

    model_name: str
    n_samples: int
    n_positive: int
    n_negative: int

    # Classification metrics at default 0.5 threshold
    accuracy: float
    precision: float
    recall: float
    f1_score: float

    # Ranking metric (primary DoD gate)
    auc_roc: float

    # Confusion matrix [[TN, FP], [FN, TP]]
    confusion_matrix: list[list[int]]

    # Optional per-threshold operating points [{threshold, precision, recall, f1}]
    threshold_analysis: list[dict[str, float]] = field(default_factory=list)

    @property
    def passes_auc_threshold(self) -> bool:
        return self.auc_roc >= 0.70

    def summary(self) -> str:
        status = "PASS" if self.passes_auc_threshold else "FAIL"
        return (
            f"{self.model_name} [{status}]\n"
            f"  n={self.n_samples} (+={self.n_positive}, -={self.n_negative})\n"
            f"  AUC-ROC:   {self.auc_roc:.4f}  (threshold ≥ 0.70)\n"
            f"  Accuracy:  {self.accuracy:.4f}\n"
            f"  Precision: {self.precision:.4f}\n"
            f"  Recall:    {self.recall:.4f}\n"
            f"  F1:        {self.f1_score:.4f}\n"
            f"  Confusion: TN={self.confusion_matrix[0][0]} "
            f"FP={self.confusion_matrix[0][1]} "
            f"FN={self.confusion_matrix[1][0]} "
            f"TP={self.confusion_matrix[1][1]}"
        )


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


class EvaluationHarness:
    """Compute offline evaluation metrics for binary classifiers.

    Args:
        model_name: Human-readable identifier written to EvaluationResult.
        n_threshold_steps: Number of threshold steps for operating-point analysis.
    """

    def __init__(
        self,
        model_name: str = "unknown",
        n_threshold_steps: int = 10,
    ) -> None:
        self._model_name = model_name
        self._n_steps = n_threshold_steps

    def evaluate(
        self,
        model: ScoringModel,
        X_test: "np.ndarray",
        y_test: "np.ndarray",
    ) -> EvaluationResult:
        """Run evaluation and return structured metrics.

        Args:
            model:  Fitted model with predict() and predict_proba() methods.
            X_test: Feature matrix (n_samples, n_features).
            y_test: Binary ground-truth labels (n_samples,).

        Returns:
            EvaluationResult with all metrics populated.
        """
        from sklearn.metrics import (
            accuracy_score,
            confusion_matrix,
            f1_score,
            precision_score,
            recall_score,
            roc_auc_score,
        )

        y_pred = model.predict(X_test)
        y_prob = model.predict_proba(X_test)[:, 1]

        n_samples = len(y_test)
        n_positive = int(np.sum(y_test))
        n_negative = n_samples - n_positive

        accuracy  = float(accuracy_score(y_test, y_pred))
        precision = float(precision_score(y_test, y_pred, zero_division=0))
        recall    = float(recall_score(y_test, y_pred, zero_division=0))
        f1        = float(f1_score(y_test, y_pred, zero_division=0))
        auc_roc   = float(roc_auc_score(y_test, y_prob))

        cm = confusion_matrix(y_test, y_pred).tolist()

        threshold_analysis = self._threshold_analysis(y_test, y_prob)

        result = EvaluationResult(
            model_name=self._model_name,
            n_samples=n_samples,
            n_positive=n_positive,
            n_negative=n_negative,
            accuracy=accuracy,
            precision=precision,
            recall=recall,
            f1_score=f1,
            auc_roc=auc_roc,
            confusion_matrix=cm,
            threshold_analysis=threshold_analysis,
        )
        logger.info(result.summary())
        return result

    def report(self, result: EvaluationResult) -> str:
        """Return a formatted evaluation report string."""
        lines = [result.summary()]
        if result.threshold_analysis:
            lines.append("  Threshold analysis:")
            for tp in result.threshold_analysis:
                lines.append(
                    f"    t={tp['threshold']:.2f}  "
                    f"P={tp['precision']:.3f}  "
                    f"R={tp['recall']:.3f}  "
                    f"F1={tp['f1']:.3f}"
                )
        return "\n".join(lines)

    def _threshold_analysis(
        self,
        y_test: "np.ndarray",
        y_prob: "np.ndarray",
    ) -> list[dict[str, float]]:
        from sklearn.metrics import f1_score, precision_score, recall_score

        thresholds = np.linspace(0.1, 0.9, self._n_steps)
        analysis = []
        for t in thresholds:
            y_pred_t = (y_prob >= t).astype(int)
            analysis.append({
                "threshold": float(t),
                "precision": float(precision_score(y_test, y_pred_t, zero_division=0)),
                "recall":    float(recall_score(y_test, y_pred_t, zero_division=0)),
                "f1":        float(f1_score(y_test, y_pred_t, zero_division=0)),
            })
        return analysis
