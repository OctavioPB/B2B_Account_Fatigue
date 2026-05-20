"""Intent Network Model — account-level intent scoring.

IntentNetworkModel wraps a scikit-learn Pipeline (StandardScaler +
LogisticRegression) trained on a labeled dataset of deal won/lost outcomes.

The model outputs an IntentScore (0–100) and a confidence value derived
from the predicted probability. Channel diversity and signal volume are
already encoded as features in the AccountFeatureVector; no manual bonus
is applied here.

Artifact lifecycle:
    - ``train.py`` trains and saves the model to ``artifacts/intent_model.joblib``
    - ``IntentNetworkModel.load(path)`` restores it at runtime
    - ``IntentNetworkModel.predict(fv)`` requires the model to be loaded
    - Tests use ``IntentNetworkModel.from_training_run(X, y)`` to build
      an ephemeral model without touching the filesystem

MODEL_VERSION must be bumped whenever training data or feature set changes.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

import numpy as np

from scoring.models import AccountFeatureVector, ChurnRiskLevel, IntentScore

logger = logging.getLogger(__name__)

MODEL_VERSION = "1.0.0"

_ARTIFACTS_DIR = os.path.join(os.path.dirname(__file__), "artifacts")
_DEFAULT_MODEL_PATH = os.path.join(_ARTIFACTS_DIR, "intent_model.joblib")


class IntentNetworkModel:
    """Logistic-regression intent classifier for B2B buying-committee signals.

    Usage::

        model = IntentNetworkModel()
        model.load()                    # load pre-trained artifact
        score = model.predict(fv)       # fv: AccountFeatureVector

        # Or for one-shot training + prediction (tests):
        model = IntentNetworkModel.from_training_run(X_train, y_train)
        scores = model.predict_batch(feature_vectors)
    """

    def __init__(self) -> None:
        self._pipeline: Any = None  # sklearn Pipeline once loaded

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def from_training_run(
        cls,
        X: "np.ndarray",
        y: "np.ndarray",
    ) -> "IntentNetworkModel":
        """Construct and immediately fit a model (used by train.py and tests)."""
        instance = cls()
        instance._fit(X, y)
        return instance

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: str = _DEFAULT_MODEL_PATH) -> None:
        """Serialise the fitted pipeline to disk using joblib."""
        import joblib

        os.makedirs(os.path.dirname(path), exist_ok=True)
        joblib.dump(self._pipeline, path)
        logger.info("IntentNetworkModel saved to %s", path)

    def load(self, path: str = _DEFAULT_MODEL_PATH) -> None:
        """Load a pre-fitted pipeline from disk."""
        import joblib

        if not os.path.exists(path):
            raise FileNotFoundError(
                f"Intent model artifact not found at {path}. "
                "Run scoring/intent/train.py to generate it."
            )
        self._pipeline = joblib.load(path)
        logger.info("IntentNetworkModel loaded from %s", path)

    # ------------------------------------------------------------------
    # Prediction
    # ------------------------------------------------------------------

    def predict(self, fv: AccountFeatureVector) -> IntentScore:
        """Predict intent score for a single account.

        Args:
            fv: Computed feature vector for the account.

        Returns:
            IntentScore with score ∈ [0, 100] and confidence ∈ [0, 1].

        Raises:
            RuntimeError: If the model has not been loaded or trained.
        """
        self._require_fitted()
        X = np.array([fv.to_feature_array()])
        prob = float(self._pipeline.predict_proba(X)[0, 1])
        score = _probability_to_score(prob)
        confidence = _compute_confidence(fv)
        breakdown = _build_intent_breakdown(fv, prob)
        return IntentScore(
            account_id=fv.account_id,
            account_domain=fv.account_domain,
            score=score,
            confidence=confidence,
            signal_breakdown=breakdown,
            model_version=MODEL_VERSION,
        )

    def predict_batch(
        self, feature_vectors: list[AccountFeatureVector]
    ) -> list[IntentScore]:
        """Predict intent scores for a batch of accounts.

        Args:
            feature_vectors: List of feature vectors (one per account).

        Returns:
            List of IntentScore objects in the same order.
        """
        self._require_fitted()
        if not feature_vectors:
            return []
        X = np.array([fv.to_feature_array() for fv in feature_vectors])
        probs = self._pipeline.predict_proba(X)[:, 1]
        return [
            IntentScore(
                account_id=fv.account_id,
                account_domain=fv.account_domain,
                score=_probability_to_score(float(prob)),
                confidence=_compute_confidence(fv),
                signal_breakdown=_build_intent_breakdown(fv, float(prob)),
                model_version=MODEL_VERSION,
            )
            for fv, prob in zip(feature_vectors, probs)
        ]

    # ------------------------------------------------------------------
    # Training (internal)
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
                C=1.0,
            )),
        ])
        self._pipeline.fit(X, y)

    def _require_fitted(self) -> None:
        if self._pipeline is None:
            raise RuntimeError(
                "IntentNetworkModel is not fitted. Call load() or "
                "IntentNetworkModel.from_training_run(X, y) first."
            )


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------


def _probability_to_score(prob: float) -> float:
    """Map logistic probability [0, 1] → IntentScore [0, 100]."""
    return round(min(100.0, max(0.0, prob * 100.0)), 2)


def _compute_confidence(fv: AccountFeatureVector) -> float:
    """Derive model confidence from signal volume and recency.

    Low signal volume → low confidence even if the score is extreme.
    Caps at 1.0. Formula: sigmoid of (log(total_30d + 1) + channel_bonus).
    """
    import math

    volume_factor = math.log1p(fv.total_signals_30d)
    channel_bonus = fv.channel_count_7d * 0.2
    raw = volume_factor + channel_bonus
    # Normalise: sigmoid centred at ~4 (≈ 55 signals over 30d)
    confidence = 1.0 / (1.0 + math.exp(-0.5 * (raw - 4.0)))
    return round(min(1.0, max(0.0, confidence)), 3)


def _build_intent_breakdown(
    fv: AccountFeatureVector, raw_prob: float
) -> dict[str, Any]:
    return {
        "raw_probability": round(raw_prob, 4),
        "total_signals_7d": fv.total_signals_7d,
        "high_intent_signals_7d": fv.high_intent_signals_7d,
        "c_suite_vp_signals_7d": fv.c_suite_vp_signals_7d,
        "channel_count_7d": fv.channel_count_7d,
        "velocity_7d": round(fv.velocity_7d, 3),
        "decayed_score_7d": round(fv.decayed_score_7d, 3),
        "committee_coverage_pct_30d": round(fv.committee_coverage_pct_30d, 3),
        "days_since_last_signal": round(fv.days_since_last_signal, 1),
    }
