# 0004: RL Orchestrator Isolated Behind Feature Flag
**Status**: Accepted
**Date**: 2026-05-17

## Context

The long-term vision for the Next Best Action (NBA) orchestrator is a reinforcement learning policy that learns optimal outreach sequences from deal outcome feedback. However, at launch:
- No production deal-outcome data exists to train on
- The reward function design is not finalized
- RL policies are harder to audit and explain to enterprise buyers than deterministic rules
- An RL policy that learns to maximize short-term engagement could increase fatigue if miscalibrated

We need to ship a working NBA engine in Sprint 7 without blocking the RL research track.

## Decision

The NBA orchestrator ships in two isolated layers:

**Layer 1 — Deterministic Rules Engine** (production-ready, Sprint 7):
- Explicit decision tree: (FatigueScore × IntentScore × ChurnProbability) → `NextBestAction`
- Fully auditable: every action has a documented rule ID and rationale
- Lives in `orchestrator/rules/`

**Layer 2 — RL Policy** (research-only until offline evaluation passes):
- Lives exclusively in `orchestrator/rl/`
- **Cannot be imported from any production code path** — enforced by a CI import boundary check
- Activated only via the `FEATURE_RL_ORCHESTRATOR=false` environment flag
- The flag defaults to `false` and must be explicitly set to `true` in any non-production environment to run experiments

Activation guard pattern (required in every RL entry point):
```python
import os
if os.getenv("FEATURE_RL_ORCHESTRATOR", "false").lower() != "true":
    raise RuntimeError(
        "RL orchestrator is disabled. Set FEATURE_RL_ORCHESTRATOR=true to enable (non-production only)."
    )
```

Promotion criteria for RL to production:
1. Offline evaluation AUC-ROC ≥ 0.80 on held-out deal-outcome dataset (min 500 deals)
2. Shadow mode A/B test: RL recommendations vs. rules engine recommendations, no statistically significant increase in account fatigue scores
3. Explicit sign-off from product owner + RevOps lead
4. New ADR documenting the promotion decision

## Consequences

- **Positive**: RL research can proceed in parallel without any production risk.
- **Positive**: Auditable rules engine satisfies enterprise buyers who want to understand why an action was recommended.
- **Constraint**: Any PR that imports `orchestrator.rl` from outside `orchestrator/rl/` must be rejected in code review. The CI schema-validation job will include an import boundary check.
- **Operational**: `FEATURE_RL_ORCHESTRATOR=true` must never appear in production `.env` files. Secret scanning should flag it as a misconfiguration.
