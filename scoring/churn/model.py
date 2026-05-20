"""Churn Predictor — 30-day deal abandonment probability.

ChurnPredictor uses the same AccountFeatureVector as IntentNetworkModel
but applies a separate logistic regression trained on churn ground truth
(deal lost / opportunity closed-lost within 30 days).

Key churn signals (anti-correlated with intent):
  - Rising negative_signals (unsubscribes, bounces, spam reports)
  - Declining velocity (signal count falling)
  - Long days_since_last_signal (disengagement)
  - Low committee_coverage_pct (only one member still engaging)
  - Absence of high_intent_signals (no pricing / demo activity)

Risk tiers (CHURN_RISK_THRESHOLDS):
  LOW      0.00 – 0.20   Monitor; no action required
  MEDIUM   0.20 – 0.50   Trigger RE_ENGAGE NBA action
  HIGH     0.50 – 0.75   Trigger EXEC_ESCALATION or DEAL_REVIEW
  CRITICAL 0.75 – 1.00   Flag for immediate human intervention

Artifact lifecycle mirrors IntentNetworkModel; see scoring/intent/model.py.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import numpy as np

from scoring.models import AccountFeatureVector, ChurnPrediction, ChurnRiskLevel

logger = logging.getLogger(__name__)

MODEL_VERSION = "1.0.0"

_ARTIFACTS_DIR = os.path.join(os.path.dirname(__file__), "artifacts")
_DEFAULT_MODEL_PATH = os.path.join(_ARTIFACTS_DIR, "churn_model.joblib")

# Probability thresholds for risk tier classification
CHURN_RISK_THRESHOLDS: dict[ChurnRiskLevel, float] = {
    ChurnRiskLevel.LOW:      0.20,
    ChurnRiskLevel.MEDIUM:   0.50,
    ChurnRiskLevel.HIGH:     0.75,
    ChurnRiskLevel.CRITICAL: 1.01,  # sentinel — everything above HIGH
}


def _classify_risk(prob: float) -> ChurnRiskLevel:
    if prob >= 0.75:
        return ChurnRiskLevel.CRITICAL
    if prob >= 0.50:
        return ChurnRiskLevel.HIGH
    if prob >= 0.20:
        return ChurnRiskLevel.MEDIUM
    return ChurnRiskLevel.LOW


class ChurnPredictor:
    """Logistic-regression 30-day churn probability classifier.

    Usage::

        predictor = ChurnPredictor()
        predictor.load()
        prediction = predictor.predict(fv)    # fv: AccountFeatureVector

        # Ephemeral (tests / train.py):
        predictor = ChurnPredictor.from_training_run(X_train, y_train)
    """

    def __init__(self) -> None:
        self._pipeline: Any = None

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def from_training_run(
        cls,
        X: "np.ndarray",
        y: "np.ndarray",
    ) -> "ChurnPredictor":
        instance = cls()
        instance._fit(X, y)
        return instance

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: str = _DEFAULT_MODEL_PATH) -> None:
        import joblib
        os.makedirs(os.path.dirname(path), exist_ok=True)
        joblib.dump(self._pipeline, path)
        logger.info("ChurnPredictor saved to %s", path)

    def load(self, path: str = _DEFAULT_MODEL_PATH) -> None:
        import joblib
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"Churn model artifact not found at {path}. "
                "Run scoring/churn/train.py to generate it."
            )
        self._pipeline = joblib.load(path)
        logger.info("ChurnPredictor loaded from %s", path)

    # ------------------------------------------------------------------
    # Prediction
    # ------------------------------------------------------------------

    def predict(self, fv: AccountFeatureVector) -> ChurnPrediction:
        """Predict 30-day churn probability for a single account.

        Returns:
            ChurnPrediction with probability ∈ [0, 1] and risk tier.
        """
        self._require_fitted()
        X = np.array([fv.to_feature_array()])
        prob = float(self._pipeline.predict_proba(X)[0, 1])
        return ChurnPrediction(
            account_id=fv.account_id,
            account_domain=fv.account_domain,
            churn_probability=round(prob, 4),
            risk_level=_classify_risk(prob),
            signal_breakdown=_build_churn_breakdown(fv, prob),
            model_version=MODEL_VERSION,
        )

    def predict_batch(
        self, feature_vectors: list[AccountFeatureVector]
    ) -> list[ChurnPrediction]:
        """Batch prediction; returns predictions in input order."""
        self._require_fitted()
        if not feature_vectors:
            return []
        X = np.array([fv.to_feature_array() for fv in feature_vectors])
        probs = self._pipeline.predict_proba(X)[:, 1]
        return [
            ChurnPrediction(
                account_id=fv.account_id,
                account_domain=fv.account_domain,
                churn_probability=round(float(prob), 4),
                risk_level=_classify_risk(float(prob)),
                signal_breakdown=_build_churn_breakdown(fv, float(prob)),
                model_version=MODEL_VERSION,
            )
            for fv, prob in zip(feature_vectors, probs)
        ]

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def _fit(self, X: "np.ndarray", y: "np.ndarray") -> None:
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler

        self._pipeline = Pipeline([
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(
                max_iter=1000,
                class_weight="balanced",
                random_state=42,
                C=0.5,   # slightly stronger regularization than intent model
            )),
        ])
        self._pipeline.fit(X, y)

    def _require_fitted(self) -> None:
        if self._pipeline is None:
            raise RuntimeError(
                "ChurnPredictor is not fitted. Call load() or "
                "ChurnPredictor.from_training_run(X, y) first."
            )


# ---------------------------------------------------------------------------
# Breakdown helper
# ---------------------------------------------------------------------------


def _build_churn_breakdown(
    fv: AccountFeatureVector, prob: float
) -> dict[str, Any]:
    return {
        "churn_probability": round(prob, 4),
        "days_since_last_signal": round(fv.days_since_last_signal, 1),
        "negative_signals_30d": fv.negative_signals_30d,
        "velocity_7d": round(fv.velocity_7d, 3),
        "velocity_14d": round(fv.velocity_14d, 3),
        "committee_coverage_pct_30d": round(fv.committee_coverage_pct_30d, 3),
        "high_intent_signals_14d": fv.high_intent_signals_14d,
        "total_signals_30d": fv.total_signals_30d,
        "risk_level": _classify_risk(prob).value,
    }
