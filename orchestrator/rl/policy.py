"""RL policy stub — ISOLATED research module.

This module is behind the FEATURE_RL_ORCHESTRATOR=true feature flag.
It must never be imported from production code paths (enforced by the
package __init__.py guard).

The RLPolicy class is a stub that returns random actions for now. It will be
replaced with a trained RLlib policy once offline evaluation benchmarks are met.

Evaluation benchmarks required before production promotion:
  - Offline A/B vs rules engine: ≥5% lift in simulated deal win rate
  - No action type produces a worse outcome than the rules engine in ≥95% of episodes
  - Coverage: all 7 action types exercised in ≥1% of decisions
  - Zero COOLDOWN false negatives: accounts with fatigue ≥ 80 always receive COOLDOWN

Usage (test environments only, FEATURE_RL_ORCHESTRATOR=true)::

    from orchestrator.rl.policy import RLPolicy
    policy = RLPolicy()
    action_type = policy.act(state_vector)
"""

from __future__ import annotations

import logging
import random
from typing import Any

# Guard: importing this module is only safe if __init__.py already passed.
# The __init__.py guard runs first; this comment is for human readers.

from orchestrator.models import ActionType

logger = logging.getLogger(__name__)

_ALL_ACTIONS = list(ActionType)


class RLPolicy:
    """Stub RL policy — returns random actions.

    Replace with a trained RLlib policy checkpoint once benchmarks are met.
    The interface must remain: act(state_vector) → ActionType.

    Args:
        checkpoint_path: Path to a trained RLlib checkpoint.
            If None (default), the stub uses random selection.
        seed: RNG seed for reproducibility in tests.
    """

    def __init__(
        self,
        checkpoint_path: str | None = None,
        seed: int | None = None,
    ) -> None:
        self._rng = random.Random(seed)
        if checkpoint_path is not None:
            logger.warning(
                "RLPolicy: checkpoint_path=%s provided but stub ignores it. "
                "Replace this class with a real RLlib policy before production.",
                checkpoint_path,
            )
        logger.warning(
            "RLPolicy (STUB) instantiated — actions are RANDOM. "
            "FEATURE_RL_ORCHESTRATOR must be disabled in production."
        )

    def act(self, state_vector: list[float]) -> ActionType:
        """Select an action given a state vector.

        Args:
            state_vector: Numeric feature vector representing account state.
                Expected length: 21 (19 intent features + fatigue_score + churn_prob).

        Returns:
            ActionType selected by the policy.
        """
        # Stub: ignore state_vector, return random action
        chosen = self._rng.choice(_ALL_ACTIONS)
        logger.debug("RLPolicy.act: state_dim=%d → %s (stub/random)", len(state_vector), chosen.value)
        return chosen

    def evaluate(self, episodes: list[dict[str, Any]]) -> dict[str, float]:
        """Stub offline evaluation — returns placeholder metrics.

        Replace with a real evaluation loop against historical deal outcomes.
        """
        return {
            "simulated_win_rate": 0.0,
            "cooldown_recall":    0.0,
            "action_coverage":    len(_ALL_ACTIONS) / len(_ALL_ACTIONS),
            "note":               "stub — no real evaluation performed",
        }
