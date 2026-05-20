"""Airflow DAG: dag_nba_orchestration

Runs every hour to compute and dispatch the Next Best Action for every active
account using the deterministic NBAOrchestrator rules engine.

Pipeline steps (TaskFlow API):
  1. fetch_active_accounts       — query dim_account for all active accounts
  2. fetch_latest_scores         — load latest intent, churn, and fatigue scores
                                   for each account from their respective tables
  3. compute_nba                 — NBAOrchestrator.decide() for every account
  4. resolve_conflicts           — apply conflict resolution against existing active NBAs
  5. persist_actions             — INSERT new NBAs; UPDATE superseded rows (is_active=FALSE)
  6. dispatch_actions            — CompositeDispatcher.dispatch_all() for new/changed actions
  7. validate_coverage           — assert 100% of active accounts have an active NBA;
                                   raise AirflowFailException (Sev-1) on any gap

Feature flag: FEATURE_RL_ORCHESTRATOR must be absent or "false".
The NBAOrchestrator constructor enforces this at instantiation time.

Environment variables:
    DATABASE_URL            — asyncpg-compatible PostgreSQL DSN
    FEATURE_RL_ORCHESTRATOR — must be unset or "false" in prod/CI
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from airflow.decorators import dag, task
from airflow.exceptions import AirflowFailException
from airflow.utils.dates import days_ago

logger = logging.getLogger(__name__)

_DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://harmoni:harmoni@localhost:5432/harmoni")

_DEFAULT_ARGS: dict[str, Any] = {
    "owner": "harmoni-orchestrator",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": False,
}


# ---------------------------------------------------------------------------
# DAG definition
# ---------------------------------------------------------------------------


@dag(
    dag_id="dag_nba_orchestration",
    description="Hourly Next Best Action computation and dispatch for all active accounts",
    schedule_interval="@hourly",
    start_date=days_ago(1),
    catchup=False,
    max_active_runs=1,
    default_args=_DEFAULT_ARGS,
    tags=["orchestrator", "nba", "rules-engine"],
)
def nba_orchestration_dag() -> None:

    # ------------------------------------------------------------------
    # Task 1: Fetch active accounts
    # ------------------------------------------------------------------

    @task()
    def fetch_active_accounts() -> list[dict[str, Any]]:
        """Query dim_account for all active (current SCD row) accounts."""
        import asyncio
        import asyncpg

        query = """
            SELECT
                id      AS account_id,
                domain  AS account_domain
            FROM dim_account
            WHERE dbt_valid_to IS NULL
              AND is_active     = TRUE
            ORDER BY domain
        """

        async def _fetch() -> list[dict]:
            conn = await asyncpg.connect(_DATABASE_URL)
            try:
                return [dict(r) for r in await conn.fetch(query)]
            finally:
                await conn.close()

        accounts = asyncio.get_event_loop().run_until_complete(_fetch())
        logger.info("Fetched %d active accounts for NBA orchestration", len(accounts))
        return accounts

    # ------------------------------------------------------------------
    # Task 2: Fetch latest scores for all active accounts
    # ------------------------------------------------------------------

    @task()
    def fetch_latest_scores(accounts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """Load the most recent intent, churn, and fatigue scores per account.

        Returns dict keyed by account_id:
            {
              "intent":  {score, confidence, ...},
              "churn":   {churn_probability, risk_level, ...},
              "fatigue": {score, severity, ...},
            }
        """
        import asyncio
        import asyncpg

        if not accounts:
            return {}

        account_ids = [a["account_id"] for a in accounts]

        intent_query = """
            SELECT DISTINCT ON (account_id)
                account_id,
                score           AS intent_score,
                confidence,
                signal_breakdown,
                model_version
            FROM account_scores
            WHERE account_id = ANY($1)
              AND score_type  = 'INTENT'
            ORDER BY account_id, computed_at DESC
        """

        churn_query = """
            SELECT DISTINCT ON (account_id)
                account_id,
                score           AS churn_probability,
                risk_level,
                model_version
            FROM account_scores
            WHERE account_id = ANY($1)
              AND score_type  = 'CHURN'
            ORDER BY account_id, computed_at DESC
        """

        fatigue_query = """
            SELECT DISTINCT ON (account_id)
                account_id,
                score           AS fatigue_score,
                severity,
                account_segment,
                components
            FROM account_fatigue_scores
            WHERE account_id = ANY($1)
            ORDER BY account_id, computed_at DESC
        """

        existing_nba_query = """
            SELECT DISTINCT ON (account_id)
                id              AS nba_id,
                account_id,
                action_type,
                priority,
                is_active,
                expires_at
            FROM next_best_actions
            WHERE account_id  = ANY($1)
              AND is_active    = TRUE
              AND expires_at   > NOW()
            ORDER BY account_id, created_at DESC
        """

        async def _fetch() -> tuple[list, list, list, list]:
            conn = await asyncpg.connect(_DATABASE_URL)
            try:
                intent  = [dict(r) for r in await conn.fetch(intent_query, account_ids)]
                churn   = [dict(r) for r in await conn.fetch(churn_query, account_ids)]
                fatigue = [dict(r) for r in await conn.fetch(fatigue_query, account_ids)]
                existing = [dict(r) for r in await conn.fetch(existing_nba_query, account_ids)]
                return intent, churn, fatigue, existing
            finally:
                await conn.close()

        intent_rows, churn_rows, fatigue_rows, existing_nba_rows = (
            asyncio.get_event_loop().run_until_complete(_fetch())
        )

        # Index by account_id
        by_account: dict[str, dict] = {a["account_id"]: {} for a in accounts}
        for r in intent_rows:
            by_account.setdefault(r["account_id"], {})["intent"] = dict(r)
        for r in churn_rows:
            by_account.setdefault(r["account_id"], {})["churn"] = dict(r)
        for r in fatigue_rows:
            by_account.setdefault(r["account_id"], {})["fatigue"] = dict(r)
        for r in existing_nba_rows:
            by_account.setdefault(r["account_id"], {})["existing_nba"] = dict(r)

        logger.info(
            "Score coverage: %d/%d intent, %d/%d churn, %d/%d fatigue",
            len(intent_rows), len(accounts),
            len(churn_rows), len(accounts),
            len(fatigue_rows), len(accounts),
        )
        return by_account

    # ------------------------------------------------------------------
    # Task 3: Compute NBA for every account
    # ------------------------------------------------------------------

    @task()
    def compute_nba(
        accounts: list[dict[str, Any]],
        scores_by_account: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Run NBAOrchestrator.decide() for every active account.

        Accounts missing one or more score types receive NURTURE (safe default).
        Returns list of serialised NextBestAction dicts.
        """
        from orchestrator.rules.engine import NBAOrchestrator
        from scoring.models import (
            AccountFatigueScore,
            ChurnPrediction,
            ChurnRiskLevel,
            FatigueSeverity,
            IntentScore,
        )

        orchestrator = NBAOrchestrator()
        as_of = datetime.now(timezone.utc)
        results = []

        for acct in accounts:
            acct_id = acct["account_id"]
            domain  = acct["account_domain"]
            scores  = scores_by_account.get(acct_id, {})

            intent_data  = scores.get("intent")
            churn_data   = scores.get("churn")
            fatigue_data = scores.get("fatigue")

            # Build model objects — use safe defaults for missing scores
            intent = IntentScore(
                account_id=acct_id,
                account_domain=domain,
                score=float(intent_data["intent_score"]) if intent_data else 0.0,
                confidence=float(intent_data.get("confidence", 0.5)) if intent_data else 0.5,
            )

            churn_prob  = float(churn_data["churn_probability"]) if churn_data else 0.0
            churn_level = (
                ChurnRiskLevel(churn_data["risk_level"]) if churn_data
                else ChurnRiskLevel.LOW
            )
            churn = ChurnPrediction(
                account_id=acct_id,
                account_domain=domain,
                churn_probability=churn_prob,
                risk_level=churn_level,
            )

            fatigue_sev   = FatigueSeverity(fatigue_data["severity"]) if fatigue_data else FatigueSeverity.LOW
            fatigue_score = float(fatigue_data["fatigue_score"]) if fatigue_data else 0.0
            fatigue = AccountFatigueScore(
                account_id=acct_id,
                account_domain=domain,
                score=fatigue_score,
                severity=fatigue_sev,
            )

            action = orchestrator.decide(acct_id, domain, fatigue, intent, churn, as_of=as_of)
            results.append(action.to_dict())

        _log_action_summary(results)
        return results

    # ------------------------------------------------------------------
    # Task 4: Resolve conflicts
    # ------------------------------------------------------------------

    @task()
    def resolve_conflicts(
        nba_decisions: list[dict[str, Any]],
        scores_by_account: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        """Apply conflict resolution between new decisions and existing active NBAs.

        Returns:
            {
              "to_insert":    [nba_dict, ...],   # new NBAs to persist
              "to_supersede": [nba_id, ...],     # existing NBA ids to deactivate
            }
        """
        from orchestrator.models import ActionType, NextBestAction, should_overwrite

        to_insert    = []
        to_supersede = []

        for nba_dict in nba_decisions:
            acct_id       = nba_dict["account_id"]
            existing_data = scores_by_account.get(acct_id, {}).get("existing_nba")

            if existing_data is None:
                to_insert.append(nba_dict)
                continue

            existing = NextBestAction(
                account_id=existing_data["account_id"],
                account_domain=nba_dict["account_domain"],
                action_type=ActionType(existing_data["action_type"]),
                rationale="existing",
                is_active=existing_data["is_active"],
            )
            incoming = NextBestAction(
                account_id=nba_dict["account_id"],
                account_domain=nba_dict["account_domain"],
                action_type=ActionType(nba_dict["action_type"]),
                rationale=nba_dict["rationale"],
            )

            if should_overwrite(existing, incoming):
                to_insert.append(nba_dict)
                to_supersede.append(existing_data["nba_id"])
            # else: existing protected action wins — no insert

        logger.info(
            "Conflict resolution: %d to insert, %d to supersede",
            len(to_insert), len(to_supersede),
        )
        return {"to_insert": to_insert, "to_supersede": to_supersede}

    # ------------------------------------------------------------------
    # Task 5: Persist actions
    # ------------------------------------------------------------------

    @task()
    def persist_actions(resolution: dict[str, Any]) -> int:
        """INSERT new NBAs and UPDATE superseded rows (is_active=FALSE).

        Returns count of new NBAs inserted.
        """
        import asyncio
        import json
        import asyncpg

        to_insert    = resolution["to_insert"]
        to_supersede = resolution["to_supersede"]

        insert_sql = """
            INSERT INTO next_best_actions (
                account_id, account_domain, action_type, priority,
                rationale, triggered_by, fatigue_score, intent_score,
                churn_probability, is_active, expires_at, created_at
            ) VALUES (
                $1, $2, $3::nba_action_type, $4, $5, $6::jsonb,
                $7, $8, $9, TRUE, $10, $11
            )
        """

        supersede_sql = """
            UPDATE next_best_actions
            SET is_active     = FALSE,
                superseded_by = NULL
            WHERE id = $1::uuid
        """

        async def _persist() -> int:
            conn = await asyncpg.connect(_DATABASE_URL)
            try:
                async with conn.transaction():
                    # Deactivate superseded actions
                    for nba_id in to_supersede:
                        await conn.execute(supersede_sql, nba_id)

                    # Insert new actions
                    rows = []
                    for n in to_insert:
                        rows.append((
                            n["account_id"],
                            n["account_domain"],
                            n["action_type"],
                            int(n["priority"]),
                            n["rationale"],
                            json.dumps(n.get("triggered_by", [])),
                            float(n["fatigue_score"]) if n.get("fatigue_score") is not None else None,
                            float(n["intent_score"])  if n.get("intent_score")  is not None else None,
                            float(n["churn_probability"]) if n.get("churn_probability") is not None else None,
                            datetime.fromisoformat(n["expires_at"]),
                            datetime.fromisoformat(n["created_at"]),
                        ))
                    await conn.executemany(insert_sql, rows)
                    return len(rows)
            finally:
                await conn.close()

        n = asyncio.get_event_loop().run_until_complete(_persist())
        logger.info("Persisted %d new NBA rows, deactivated %d", n, len(to_supersede))
        return n

    # ------------------------------------------------------------------
    # Task 6: Dispatch actions
    # ------------------------------------------------------------------

    @task()
    def dispatch_actions(resolution: dict[str, Any]) -> dict[str, int]:
        """Dispatch new NBAs to all registered platforms via CompositeDispatcher.

        Returns summary: {"dispatched": N, "failed": M}
        """
        from orchestrator.actions.dispatcher import (
            CompositeDispatcher,
            HubSpotDispatcher,
            SalesloftDispatcher,
            SlackDispatcher,
        )
        from orchestrator.models import ActionType, NextBestAction

        dispatcher = CompositeDispatcher([
            HubSpotDispatcher(),
            SalesloftDispatcher(),
            SlackDispatcher(),
        ])

        n_dispatched = 0
        n_failed = 0

        for nba_dict in resolution["to_insert"]:
            action = NextBestAction(
                account_id=nba_dict["account_id"],
                account_domain=nba_dict["account_domain"],
                action_type=ActionType(nba_dict["action_type"]),
                rationale=nba_dict["rationale"],
                triggered_by=nba_dict.get("triggered_by", []),
                fatigue_score=nba_dict.get("fatigue_score"),
                intent_score=nba_dict.get("intent_score"),
                churn_probability=nba_dict.get("churn_probability"),
            )
            results = dispatcher.dispatch_all(action)
            if all(r.success for r in results):
                n_dispatched += 1
            else:
                n_failed += 1
                logger.warning(
                    "Partial dispatch failure for account=%s action=%s",
                    action.account_domain, action.action_type.value,
                )

        logger.info("Dispatch complete: %d succeeded, %d failed", n_dispatched, n_failed)
        return {"dispatched": n_dispatched, "failed": n_failed}

    # ------------------------------------------------------------------
    # Task 7: Validate coverage
    # ------------------------------------------------------------------

    @task()
    def validate_coverage(
        accounts: list[dict[str, Any]],
        n_inserted: int,
        resolution: dict[str, Any],
    ) -> None:
        """Assert 100% of active accounts have an active NBA after this run.

        An account that was NOT inserted (conflict resolution kept existing) is
        still covered — we only fail if an account has no active NBA at all.
        """
        import asyncio
        import asyncpg

        account_ids = [a["account_id"] for a in accounts]
        n_active = len(account_ids)

        check_sql = """
            SELECT COUNT(DISTINCT account_id) AS covered
            FROM next_best_actions
            WHERE account_id = ANY($1)
              AND is_active   = TRUE
              AND expires_at  > NOW()
        """

        async def _check() -> int:
            conn = await asyncpg.connect(_DATABASE_URL)
            try:
                row = await conn.fetchrow(check_sql, account_ids)
                return int(row["covered"])
            finally:
                await conn.close()

        n_covered = asyncio.get_event_loop().run_until_complete(_check())

        if n_covered < n_active:
            raise AirflowFailException(
                f"[SEV-1] NBA coverage gap: {n_active - n_covered} active accounts "
                f"have no active NBA (expected {n_active}, covered {n_covered})"
            )
        logger.info(
            "Coverage validation PASSED — %d/%d accounts have active NBAs",
            n_covered, n_active,
        )

    # ------------------------------------------------------------------
    # Wire up task dependencies
    # ------------------------------------------------------------------

    active_accounts  = fetch_active_accounts()
    scores           = fetch_latest_scores(active_accounts)
    nba_decisions    = compute_nba(active_accounts, scores)
    resolution       = resolve_conflicts(nba_decisions, scores)
    n_inserted       = persist_actions(resolution)

    dispatch_actions(resolution)
    validate_coverage(active_accounts, n_inserted, resolution)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _log_action_summary(nba_dicts: list[dict[str, Any]]) -> None:
    counts: dict[str, int] = {}
    for n in nba_dicts:
        counts[n["action_type"]] = counts.get(n["action_type"], 0) + 1
    summary = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
    logger.info("NBA action distribution: %s", summary)


# Register with Airflow
dag_instance = nba_orchestration_dag()
