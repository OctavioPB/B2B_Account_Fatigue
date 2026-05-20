"""Training script for IntentNetworkModel.

Generates a synthetic labeled dataset, trains a logistic regression pipeline,
evaluates it on a held-out test set, asserts AUC-ROC ≥ 0.70, and saves the
artifact to scoring/intent/artifacts/intent_model.joblib.

Run::

    python -m scoring.intent.train

Environment variables:
    INTENT_MODEL_PATH   — override default artifact path
    INTENT_N_SAMPLES    — number of synthetic training samples (default 2000)
    INTENT_RANDOM_SEED  — random seed (default 42)

Synthetic label heuristic
--------------------------
A "won deal" (label=1) is associated with accounts that show:
  - High volume of strong/high-intent signals in last 7d
  - Positive velocity (signal count rising)
  - Senior stakeholder engagement (C-suite / VP)
  - Multi-channel activity (≥ 2 channels)
  - Low negative signal count

We encode this as a weighted sum of features passed through a sigmoid,
then add Gaussian noise to simulate real-world label uncertainty.
"""

from __future__ import annotations

import logging
import os
import sys

import numpy as np

from scoring.evaluation.harness import EvaluationHarness
from scoring.intent.model import IntentNetworkModel
from scoring.models import FEATURE_NAMES

logger = logging.getLogger(__name__)

_N_SAMPLES    = int(os.getenv("INTENT_N_SAMPLES", "2000"))
_RANDOM_SEED  = int(os.getenv("INTENT_RANDOM_SEED", "42"))
_MODEL_PATH   = os.getenv(
    "INTENT_MODEL_PATH",
    os.path.join(os.path.dirname(__file__), "artifacts", "intent_model.joblib"),
)
_AUC_THRESHOLD = 0.70


def generate_synthetic_data(
    n_samples: int = _N_SAMPLES,
    random_state: int = _RANDOM_SEED,
) -> tuple["np.ndarray", "np.ndarray"]:
    """Generate (X, y) for intent model training.

    Feature columns follow FEATURE_NAMES order. Labels are derived from
    a hand-crafted linear scoring rule + noise, giving a separable but
    noisy binary classification problem.

    Returns:
        X: (n_samples, n_features) float array.
        y: (n_samples,) binary int array (1 = high intent / deal won).
    """
    rng = np.random.default_rng(random_state)
    n = n_samples

    # ---- Sample raw feature distributions ----
    # total_signals_7d
    total_7d  = rng.integers(0, 60, size=n).astype(float)
    # total_signals_14d  >= total_7d
    total_14d = total_7d + rng.integers(0, 60, size=n).astype(float)
    # total_signals_30d  >= total_14d
    total_30d = total_14d + rng.integers(0, 80, size=n).astype(float)

    strong_7d  = (total_7d  * rng.uniform(0, 0.6, n)).astype(float)
    strong_14d = (total_14d * rng.uniform(0, 0.6, n)).astype(float)
    hi_7d      = (total_7d  * rng.uniform(0, 0.5, n)).astype(float)
    hi_14d     = (total_14d * rng.uniform(0, 0.5, n)).astype(float)
    neg_7d     = rng.integers(0, 5,  size=n).astype(float)
    neg_30d    = rng.integers(0, 10, size=n).astype(float)

    unique_m_7d  = np.clip(rng.integers(0, 8, size=n).astype(float), 0, total_7d)
    unique_m_30d = np.clip(rng.integers(0, 10, size=n).astype(float), 0, total_30d)

    channel_7d = rng.integers(0, 5, size=n).astype(float)

    role_ws_7d = total_7d * rng.uniform(0, 1.5, n)
    cs_vp_7d   = rng.integers(0, 6, size=n).astype(float)

    coverage   = rng.uniform(0, 1, n)
    vel_7d     = rng.uniform(-1, 5, n)
    vel_14d    = rng.uniform(-1, 5, n)

    days_since = rng.exponential(scale=10, size=n)   # median ~10 days

    # decayed_score correlated with total_7d
    decayed    = total_7d * rng.uniform(0.5, 1.5, n)

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

    # ---- Synthetic labels: intent score = weighted sum of key signals ----
    # Positive weights → more intent. Negative weights → less intent.
    weights = np.array([
        0.08,   # total_signals_7d
        0.03,   # total_signals_14d
        0.01,   # total_signals_30d
        0.12,   # strong_signals_7d
        0.04,   # strong_signals_14d
        0.20,   # high_intent_signals_7d     ← strongest positive signal
        0.08,   # high_intent_signals_14d
        -0.30,  # negative_signals_7d        ← strongest negative signal
        -0.10,  # negative_signals_30d
        0.05,   # unique_members_7d
        0.02,   # unique_members_30d
        0.10,   # channel_count_7d
        0.06,   # role_weighted_score_7d
        0.15,   # c_suite_vp_signals_7d
        0.08,   # committee_coverage_pct_30d
        0.12,   # velocity_7d
        0.04,   # velocity_14d
        -0.05,  # days_since_last_signal
        0.03,   # decayed_score_7d
    ])

    # Standardise X before applying weights (mimics the real pipeline)
    X_std = (X - X.mean(axis=0)) / (X.std(axis=0) + 1e-8)
    logit = X_std @ weights + rng.normal(0, 0.5, n)  # noise
    prob  = 1.0 / (1.0 + np.exp(-logit))
    y     = (prob > 0.5).astype(int)

    return X, y


def train(
    n_samples: int = _N_SAMPLES,
    random_state: int = _RANDOM_SEED,
    model_path: str = _MODEL_PATH,
    *,
    save: bool = True,
) -> tuple[IntentNetworkModel, float]:
    """Train the intent model, evaluate it, assert AUC-ROC ≥ 0.70.

    Args:
        n_samples:    Number of synthetic samples.
        random_state: RNG seed for reproducibility.
        model_path:   Where to save the artifact.
        save:         If False, skip saving (used in tests).

    Returns:
        (fitted_model, auc_roc)

    Raises:
        SystemExit: If AUC-ROC < 0.70 (training failed DoD gate).
    """
    from sklearn.model_selection import train_test_split

    logger.info("Generating %d synthetic samples (seed=%d)…", n_samples, random_state)
    X, y = generate_synthetic_data(n_samples, random_state)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=random_state, stratify=y
    )

    logger.info(
        "Training set: %d samples (%d positive), "
        "Test set: %d samples (%d positive)",
        len(X_train), int(y_train.sum()),
        len(X_test),  int(y_test.sum()),
    )

    model = IntentNetworkModel.from_training_run(X_train, y_train)

    harness = EvaluationHarness(model_name=f"IntentNetworkModel v{model.MODEL_VERSION}")
    result  = harness.evaluate(model._pipeline, X_test, y_test)

    print(harness.report(result))

    if not result.passes_auc_threshold:
        logger.error(
            "AUC-ROC %.4f < 0.70 threshold — model does not meet DoD. "
            "Adjust feature set or increase training data.",
            result.auc_roc,
        )
        sys.exit(1)

    if save:
        model.save(model_path)
        logger.info("Model artifact saved to %s", model_path)

    return model, result.auc_roc


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    _model, _auc = train()
    print(f"\nTraining complete. AUC-ROC = {_auc:.4f}")
