"""harmoni · RL experiments — ISOLATED, never imported from production paths.

CLAUDE.md Hard Rule #4:
  "Reinforcement learning code lives only in orchestrator/rl/. It must be behind
   the FEATURE_RL_ORCHESTRATOR=false flag. Production NBA actions use the
   deterministic rules engine until the RL policy passes offline evaluation
   benchmarks."

This guard runs at import time. Any production code path that accidentally
imports this module when FEATURE_RL_ORCHESTRATOR is not explicitly "true" will
raise ImportError immediately, making the violation visible in tests and CI.
"""

from __future__ import annotations

import os

_flag = os.getenv("FEATURE_RL_ORCHESTRATOR", "false").strip().lower()

if _flag != "true":
    raise ImportError(
        "orchestrator.rl may only be imported when FEATURE_RL_ORCHESTRATOR=true. "
        "This module is isolated from all production code paths per CLAUDE.md Hard Rule #4. "
        "If you are writing a test for the RL policy, set the env var explicitly in your "
        "test fixture. If you reached this from production code, remove the import."
    )
