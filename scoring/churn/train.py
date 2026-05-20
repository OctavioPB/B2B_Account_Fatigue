"""Training script for ChurnPredictor.

Generates synthetic labeled dataset where label=1 represents a churned deal
(opportunity closed-lost within 30 days), trains a logistic regression, and
asserts AUC-ROC ≥ 0.70. Saves the artifact to
scoring/churn/artifacts/churn_model.joblib.

Run::

    python -m scoring.churn.train

Churn label heuristic
---------------------
A "churned deal" (label=1) is associated with accounts that show:
  - Long days_since_last_signal (disengagement)
  - Rising negative signals (unsubscribes, bounces, spam)
  - Declining velocity (signal count falling)
  - Low committee coverage (only one member still engaging)
  - Absence of high-intent signals (no pricing/demo activity recently)
  - Weak role-weighted score (only low-seniority members active)
"""

from __future__ import annotations

import logging
import os
import sys

import numpy as np

from scoring.churn.model import ChurnPredictor
from scoring.evaluation.harness import EvaluationHarness
from scoring.models import FEATURE_NAMES

logger = logging.getLogger(__name__)

_N_SAMPLES   = int(os.getenv("CHURN_N_SAMPLES", "2000"))
_RANDOM_SEED = int(os.getenv("CHURN_RANDOM_SEED", "42"))
_MODEL_PATH  = os.getenv(
    "CHURN_MODEL_PATH",
    os.path.join(os.path.dirname(__file__), "artifacts", "churn_model.joblib"),
)
_AUC_THRESHOLD = 0.70


def generate_synthetic_churn_data(
    n_samples: int = _N_SAMPLES,
    random_state: int = _RANDOM_SEED,
) -> tuple["np.ndarray", "np.ndarray"]:
    """Generate (X, y) for churn model training.

    X columns follow FEATURE_NAMES order (same as intent model).
    y=1 means the account churned within 30 days.
    """
    rng = np.random.default_rng(random_state)
    n = n_samples

    total_7d  = rng.integers(0, 40, size=n).astype(float)
    total_14d = total_7d + rng.integers(0, 40, size=n).astype(float)
    total_30d = total_14d + rng.integers(0, 60, size=n).astype(float)

    strong_7d  = (total_7d  * rng.uniform(0, 0.4, n)).astype(float)
    strong_14d = (total_14d * rng.uniform(0, 0.4, n)).astype(float)
    hi_7d      = (total_7d  * rng.uniform(0, 0.3, n)).astype(float)
    hi_14d     = (total_14d * rng.uniform(0, 0.3, n)).astype(float)
    neg_7d     = rng.integers(0, 8,  size=n).astype(float)
    neg_30d    = rng.integers(0, 20, size=n).astype(float)

    unique_m_7d  = np.clip(rng.integers(0, 6, size=n).astype(float), 0, total_7d)
    unique_m_30d = np.clip(rng.integers(0, 8, size=n).astype(float), 0, total_30d)
    channel_7d   = rng.integers(0, 5, size=n).astype(float)

    role_ws_7d = total_7d * rng.uniform(0, 1.0, n)
    cs_vp_7d   = rng.integers(0, 4, size=n).astype(float)

    coverage   = rng.uniform(0, 1, n)
    vel_7d     = rng.uniform(-1, 3, n)
    vel_14d    = rng.uniform(-1, 3, n)
    days_since = rng.exponential(scale=15, size=n)  # higher mean → more likely to churn
    decayed    = total_7d * rng.uniform(0.3, 1.2, n)

    X = np.column_stack([
        total_7d, total_14d, total_30d,
        strong_7d, strong_14d,
        hi_7d, hi_14d,
        neg_7d, neg_30d,
        unique_m_7d, unique_m_30d,
        channel_7d,
        role_ws_7d, cs_vp_7d,
        coverage,
        vel_7d, vel_14d,
        days_since,
        decayed,
    ])

    # Churn is anti-correlated with intent signals
    weights = np.array([
        -0.06,  # total_signals_7d
        -0.02,  # total_signals_14d
        -0.01,  # total_signals_30d
        -0.08,  # strong_signals_7d
        -0.03,  # strong_signals_14d
        -0.18,  # high_intent_signals_7d    ← strong negative for churn
        -0.06,  # high_intent_signals_14d
         0.28,  # negative_signals_7d       ← strongest positive for churn
         0.12,  # negative_signals_30d
        -0.04,  # unique_members_7d
        -0.02,  # unique_members_30d
        -0.08,  # channel_count_7d
        -0.05,  # role_weighted_score_7d
        -0.12,  # c_suite_vp_signals_7d
        -0.10,  # committee_coverage_pct_30d
        -0.14,  # velocity_7d               ← negative velocity → churn risk
        -0.05,  # velocity_14d
         0.08,  # days_since_last_signal     ← disengagement
        -0.02,  # decayed_score_7d
    ])

    X_std = (X - X.mean(axis=0)) / (X.std(axis=0) + 1e-8)
    logit = X_std @ weights + rng.normal(0, 0.5, n)
    prob  = 1.0 / (1.0 + np.exp(-logit))
    y     = (prob > 0.5).astype(int)

    return X, y


def train(
    n_samples: int = _N_SAMPLES,
    random_state: int = _RANDOM_SEED,
    model_path: str = _MODEL_PATH,
    *,
    save: bool = True,
) -> tuple[ChurnPredictor, float]:
    """Train the churn model, evaluate, assert AUC-ROC ≥ 0.70.

    Returns:
        (fitted_predictor, auc_roc)
    """
    from sklearn.model_selection import train_test_split

    logger.info("Generating %d synthetic churn samples (seed=%d)…", n_samples, random_state)
    X, y = generate_synthetic_churn_data(n_samples, random_state)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=random_state, stratify=y
    )

    logger.info(
        "Training: %d samples (%d churn), Test: %d samples (%d churn)",
        len(X_train), int(y_train.sum()), len(X_test), int(y_test.sum()),
    )

    predictor = ChurnPredictor.from_training_run(X_train, y_train)

    harness = EvaluationHarness(model_name=f"ChurnPredictor v{predictor.MODEL_VERSION}")
    result  = harness.evaluate(predictor._pipeline, X_test, y_test)

    print(harness.report(result))

    if not result.passes_auc_threshold:
        logger.error(
            "AUC-ROC %.4f < 0.70 threshold — churn model does not meet DoD.",
            result.auc_roc,
        )
        sys.exit(1)

    if save:
        predictor.save(model_path)
        logger.info("Churn model artifact saved to %s", model_path)

    return predictor, result.auc_roc


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    _predictor, _auc = train()
    print(f"\nChurn training complete. AUC-ROC = {_auc:.4f}")
