"""Airflow DAG: dag_intent_score_refresh

Runs every 4 hours to recompute IntentScore and ChurnPrediction for every
active account and persist results to the account_scores table in PostgreSQL.

Pipeline steps (TaskFlow API):
  1. load_models        — load intent + churn joblib artifacts; fail fast if missing
  2. fetch_active_accounts — query dim_account for all active accounts
  3. fetch_signal_data  — load fct_account_signal_hourly + fct_committee_engagement
                          for the rolling 30-day window
  4. compute_features   — run FeatureEngineer.compute() for each account
  5. score_intent       — IntentNetworkModel.predict_batch()
  6. score_churn        — ChurnPredictor.predict_batch()
  7. persist_scores     — bulk-upsert scores into account_scores table
  8. validate_coverage  — assert 100% of active accounts received a score this run;
                          raise AirflowFailException if any are missing

Environment variables consumed:
    DATABASE_URL         — asyncpg-compatible PostgreSQL DSN
    INTENT_MODEL_PATH    — override default artifact path
    CHURN_MODEL_PATH     — override default artifact path
    DBT_TARGET           — dbt profile target (used by upstream DAG only)

Dependency: dag_hourly_account_metrics must have completed at least once
to populate dim_account, fct_account_signal_hourly, and fct_committee_engagement.

FEATURE_FLAG: FEATURE_RL_ORCHESTRATOR must remain false. This DAG feeds the
deterministic NBA rules engine, not the RL policy.
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

# ---------------------------------------------------------------------------
# DAG-level constants
# ---------------------------------------------------------------------------

_DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://harmoni:harmoni@localhost:5432/harmoni")

_INTENT_MODEL_PATH = os.getenv(
    "INTENT_MODEL_PATH",
    os.path.join(
        os.path.dirname(__file__),
        "../../scoring/intent/artifacts/intent_model.joblib",
    ),
)
_CHURN_MODEL_PATH = os.getenv(
    "CHURN_MODEL_PATH",
    os.path.join(
        os.path.dirname(__file__),
        "../../scoring/churn/artifacts/churn_model.joblib",
    ),
)

_SIGNAL_LOOKBACK_DAYS = 30

_DEFAULT_ARGS: dict[str, Any] = {
    "owner": "harmoni-ml",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": False,
}


# ---------------------------------------------------------------------------
# DAG definition
# ---------------------------------------------------------------------------


@dag(
    dag_id="dag_intent_score_refresh",
    description="4-hourly intent and churn score refresh for all active accounts",
    schedule_interval="0 */4 * * *",
    start_date=days_ago(1),
    catchup=False,
    max_active_runs=1,
    default_args=_DEFAULT_ARGS,
    tags=["scoring", "intent", "churn", "ml"],
)
def intent_score_refresh_dag() -> None:

    # ------------------------------------------------------------------
    # Task 1: Load ML model artifacts
    # ------------------------------------------------------------------

    @task()
    def load_models() -> dict[str, str]:
        """Verify both model artifacts exist and are loadable.

        Returns paths dict so downstream tasks use the same resolved paths.
        Fails fast if either artifact is missing — avoids scoring partial
        results with mismatched model versions.
        """
        import joblib

        intent_path = os.path.normpath(_INTENT_MODEL_PATH)
        churn_path  = os.path.normpath(_CHURN_MODEL_PATH)

        for label, path in [("intent", intent_path), ("churn", churn_path)]:
            if not os.path.exists(path):
                raise FileNotFoundError(
                    f"{label} model artifact not found at {path}. "
                    f"Run scoring/{label}/train.py to generate it."
                )
            # Quick loadability check — catches corrupt files before scoring starts
            joblib.load(path)
            logger.info("Verified %s model artifact: %s", label, path)

        return {"intent_path": intent_path, "churn_path": churn_path}

    # ------------------------------------------------------------------
    # Task 2: Fetch active accounts
    # ------------------------------------------------------------------

    @task()
    def fetch_active_accounts() -> list[dict[str, Any]]:
        """Query dim_account for all active (non-churned, current SCD row) accounts.

        Returns list of dicts: [{account_id, account_domain, committee_size}].
        committee_size is used by FeatureEngineer to compute coverage %.
        """
        import asyncio
        import asyncpg

        query = """
            SELECT
                a.id                    AS account_id,
                a.domain                AS account_domain,
                COUNT(m.id)             AS committee_size
            FROM dim_account a
            LEFT JOIN dim_committee_member m
                   ON m.account_id = a.id
                  AND m.is_active  = TRUE
            WHERE a.dbt_valid_to IS NULL   -- current SCD row
              AND a.is_active     = TRUE
            GROUP BY a.id, a.domain
            ORDER BY a.domain
        """

        async def _fetch() -> list[dict]:
            conn = await asyncpg.connect(_DATABASE_URL)
            try:
                rows = await conn.fetch(query)
                return [dict(r) for r in rows]
            finally:
                await conn.close()

        accounts = asyncio.get_event_loop().run_until_complete(_fetch())
        logger.info("Fetched %d active accounts for scoring", len(accounts))
        if not accounts:
            logger.warning("No active accounts found — nothing to score this run")
        return accounts

    # ------------------------------------------------------------------
    # Task 3: Fetch signal data for all active accounts
    # ------------------------------------------------------------------

    @task()
    def fetch_signal_data(accounts: list[dict[str, Any]]) -> dict[str, Any]:
        """Load rolling 30-day signal rows for all active accounts.

        Returns a nested dict keyed by account_domain:
          {
            "signals":        {domain: [SignalRow dicts]},
            "member_signals": {domain: [MemberEngagementRow dicts]},
          }
        """
        import asyncio
        import asyncpg

        if not accounts:
            return {"signals": {}, "member_signals": {}}

        domains = [a["account_domain"] for a in accounts]
        cutoff  = datetime.now(timezone.utc) - timedelta(days=_SIGNAL_LOOKBACK_DAYS)

        signal_query = """
            SELECT
                s.account_domain,
                s.signal_hour::date     AS signal_date,
                s.source_system,
                SUM(s.signal_count)     AS signal_count,
                SUM(s.strong_signal_count)      AS strong_signal_count,
                SUM(s.high_intent_signal_count) AS high_intent_signal_count,
                SUM(s.negative_signal_count)    AS negative_signal_count,
                COUNT(DISTINCT s.unique_member_count)   AS unique_member_count,
                SUM(s.total_strength_score)     AS total_strength_score
            FROM fct_account_signal_hourly s
            WHERE s.account_domain = ANY($1)
              AND s.signal_hour    >= $2
            GROUP BY s.account_domain, s.signal_hour::date, s.source_system
        """

        member_query = """
            SELECT
                e.account_domain,
                e.signal_day            AS signal_date,
                e.member_id,
                m.seniority_level,
                m.role_weight,
                SUM(e.signal_count)           AS signal_count,
                SUM(e.weighted_signal_score)  AS weighted_signal_score,
                SUM(e.high_intent_signal_count) AS high_intent_count,
                SUM(e.negative_signal_count)    AS negative_count
            FROM fct_committee_engagement e
            JOIN dim_committee_member m ON m.id = e.member_id AND m.dbt_valid_to IS NULL
            WHERE e.account_domain = ANY($1)
              AND e.signal_day     >= $2
            GROUP BY e.account_domain, e.signal_day, e.member_id,
                     m.seniority_level, m.role_weight
        """

        async def _fetch() -> tuple[list[dict], list[dict]]:
            conn = await asyncpg.connect(_DATABASE_URL)
            try:
                signals = [dict(r) for r in await conn.fetch(signal_query, domains, cutoff)]
                members = [dict(r) for r in await conn.fetch(member_query, domains, cutoff)]
                return signals, members
            finally:
                await conn.close()

        raw_signals, raw_members = asyncio.get_event_loop().run_until_complete(_fetch())

        # Group by account domain for fast per-account lookup
        signals_by_domain: dict[str, list[dict]] = {}
        for row in raw_signals:
            domain = row["account_domain"]
            signals_by_domain.setdefault(domain, []).append(row)

        members_by_domain: dict[str, list[dict]] = {}
        for row in raw_members:
            domain = row["account_domain"]
            members_by_domain.setdefault(domain, []).append(row)

        logger.info(
            "Fetched signal data: %d signal rows, %d member rows across %d domains",
            len(raw_signals), len(raw_members), len(domains),
        )
        return {"signals": signals_by_domain, "member_signals": members_by_domain}

    # ------------------------------------------------------------------
    # Task 4: Compute feature vectors
    # ------------------------------------------------------------------

    @task()
    def compute_features(
        accounts: list[dict[str, Any]],
        signal_data: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Run FeatureEngineer.compute() for every active account.

        Returns list of serialised AccountFeatureVector dicts (via .to_dict()).
        """
        from scoring.intent.features import FeatureEngineer
        from scoring.models import MemberEngagementRow, SignalRow

        fe = FeatureEngineer()
        as_of = datetime.now(timezone.utc)
        signals_by_domain  = signal_data["signals"]
        members_by_domain  = signal_data["member_signals"]

        feature_vectors = []
        for acct in accounts:
            domain = acct["account_domain"]

            raw_signals = signals_by_domain.get(domain, [])
            signal_rows = [
                SignalRow(
                    signal_date=row["signal_date"] if isinstance(row["signal_date"], datetime)
                                else datetime.fromisoformat(str(row["signal_date"])).replace(tzinfo=timezone.utc),
                    source_system=row["source_system"],
                    signal_count=int(row.get("signal_count", 0)),
                    strong_signal_count=int(row.get("strong_signal_count", 0)),
                    high_intent_signal_count=int(row.get("high_intent_signal_count", 0)),
                    negative_signal_count=int(row.get("negative_signal_count", 0)),
                    unique_member_count=int(row.get("unique_member_count", 0)),
                    total_strength_score=float(row.get("total_strength_score", 0.0)),
                )
                for row in raw_signals
            ]

            raw_members = members_by_domain.get(domain, [])
            member_rows = [
                MemberEngagementRow(
                    signal_date=row["signal_date"] if isinstance(row["signal_date"], datetime)
                                else datetime.fromisoformat(str(row["signal_date"])).replace(tzinfo=timezone.utc),
                    member_id=row["member_id"],
                    seniority_level=row.get("seniority_level", "IC"),
                    role_weight=float(row.get("role_weight", 0.2)),
                    signal_count=int(row.get("signal_count", 0)),
                    weighted_signal_score=float(row.get("weighted_signal_score", 0.0)),
                    high_intent_count=int(row.get("high_intent_count", 0)),
                    negative_count=int(row.get("negative_count", 0)),
                )
                for row in raw_members
            ]

            fv = fe.compute(
                account_id=acct["account_id"],
                account_domain=domain,
                signals=signal_rows,
                member_signals=member_rows,
                committee_size=int(acct.get("committee_size", 0)),
                as_of=as_of,
            )
            feature_vectors.append(fv.to_dict())

        logger.info("Computed feature vectors for %d accounts", len(feature_vectors))
        return feature_vectors

    # ------------------------------------------------------------------
    # Task 5: Intent scoring
    # ------------------------------------------------------------------

    @task()
    def score_intent(
        feature_vectors: list[dict[str, Any]],
        model_paths: dict[str, str],
    ) -> list[dict[str, Any]]:
        """Run IntentNetworkModel.predict_batch(); return serialised IntentScore list."""
        from scoring.intent.model import IntentNetworkModel
        from scoring.models import AccountFeatureVector

        model = IntentNetworkModel()
        model.load(model_paths["intent_path"])

        fvs = [AccountFeatureVector(**_deserialize_fv(d)) for d in feature_vectors]
        results = model.predict_batch(fvs)

        serialised = [
            {
                "account_id":     r.account_id,
                "account_domain": r.account_domain,
                "score_type":     "INTENT",
                "score":          r.score,
                "confidence":     r.confidence,
                "signal_breakdown": r.signal_breakdown,
                "model_version":  r.model_version,
            }
            for r in results
        ]
        logger.info(
            "Intent scores computed: %d accounts (avg score %.1f)",
            len(serialised),
            sum(s["score"] for s in serialised) / max(len(serialised), 1),
        )
        return serialised

    # ------------------------------------------------------------------
    # Task 6: Churn scoring
    # ------------------------------------------------------------------

    @task()
    def score_churn(
        feature_vectors: list[dict[str, Any]],
        model_paths: dict[str, str],
    ) -> list[dict[str, Any]]:
        """Run ChurnPredictor.predict_batch(); return serialised ChurnPrediction list."""
        from scoring.churn.model import ChurnPredictor
        from scoring.models import AccountFeatureVector

        predictor = ChurnPredictor()
        predictor.load(model_paths["churn_path"])

        fvs = [AccountFeatureVector(**_deserialize_fv(d)) for d in feature_vectors]
        results = predictor.predict_batch(fvs)

        serialised = [
            {
                "account_id":       r.account_id,
                "account_domain":   r.account_domain,
                "score_type":       "CHURN",
                "churn_probability": r.churn_probability,
                "risk_level":       r.risk_level.value,
                "signal_breakdown": r.signal_breakdown,
                "model_version":    r.model_version,
            }
            for r in results
        ]
        logger.info(
            "Churn scores computed: %d accounts (avg prob %.3f, high/critical: %d)",
            len(serialised),
            sum(s["churn_probability"] for s in serialised) / max(len(serialised), 1),
            sum(1 for s in serialised if s["risk_level"] in ("HIGH", "CRITICAL")),
        )
        return serialised

    # ------------------------------------------------------------------
    # Task 7: Persist scores
    # ------------------------------------------------------------------

    @task()
    def persist_scores(
        intent_scores: list[dict[str, Any]],
        churn_scores: list[dict[str, Any]],
        feature_vectors: list[dict[str, Any]],
    ) -> dict[str, int]:
        """Bulk-upsert intent and churn scores to account_scores table.

        Uses INSERT ... ON CONFLICT DO UPDATE to allow idempotent re-runs.
        Returns {"intent_upserted": N, "churn_upserted": N}.
        """
        import asyncio
        import json
        import asyncpg

        fv_by_account_id = {d["account_id"]: d for d in feature_vectors}

        upsert_sql = """
            INSERT INTO account_scores (
                account_id, score_type, score_value, churn_probability,
                churn_risk_level, confidence, signal_breakdown,
                feature_vector, model_version, scored_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb, $9, now())
            ON CONFLICT (account_id, score_type)
            DO UPDATE SET
                score_value       = EXCLUDED.score_value,
                churn_probability = EXCLUDED.churn_probability,
                churn_risk_level  = EXCLUDED.churn_risk_level,
                confidence        = EXCLUDED.confidence,
                signal_breakdown  = EXCLUDED.signal_breakdown,
                feature_vector    = EXCLUDED.feature_vector,
                model_version     = EXCLUDED.model_version,
                scored_at         = EXCLUDED.scored_at
        """

        def _intent_row(s: dict) -> tuple:
            fv = fv_by_account_id.get(s["account_id"], {})
            return (
                s["account_id"], "INTENT",
                s["score"], None, None,
                s["confidence"],
                json.dumps(s["signal_breakdown"]),
                json.dumps(fv),
                s["model_version"],
            )

        def _churn_row(s: dict) -> tuple:
            fv = fv_by_account_id.get(s["account_id"], {})
            return (
                s["account_id"], "CHURN",
                None, s["churn_probability"], s["risk_level"],
                None,
                json.dumps(s["signal_breakdown"]),
                json.dumps(fv),
                s["model_version"],
            )

        async def _persist() -> tuple[int, int]:
            conn = await asyncpg.connect(_DATABASE_URL)
            try:
                async with conn.transaction():
                    intent_rows = [_intent_row(s) for s in intent_scores]
                    await conn.executemany(upsert_sql, intent_rows)

                    churn_rows = [_churn_row(s) for s in churn_scores]
                    await conn.executemany(upsert_sql, churn_rows)

                return len(intent_rows), len(churn_rows)
            finally:
                await conn.close()

        n_intent, n_churn = asyncio.get_event_loop().run_until_complete(_persist())
        logger.info("Persisted %d intent scores, %d churn scores", n_intent, n_churn)
        return {"intent_upserted": n_intent, "churn_upserted": n_churn}

    # ------------------------------------------------------------------
    # Task 8: Validate coverage
    # ------------------------------------------------------------------

    @task()
    def validate_coverage(
        accounts: list[dict[str, Any]],
        persist_result: dict[str, int],
    ) -> None:
        """Assert 100% of active accounts received both an intent and churn score.

        Raises AirflowFailException (Sev-1) if any active account is missing
        a score for this run.
        """
        n_active  = len(accounts)
        n_intent  = persist_result["intent_upserted"]
        n_churn   = persist_result["churn_upserted"]

        errors = []
        if n_intent < n_active:
            errors.append(
                f"Intent coverage gap: {n_active - n_intent} active accounts missing scores"
            )
        if n_churn < n_active:
            errors.append(
                f"Churn coverage gap: {n_active - n_churn} active accounts missing scores"
            )

        if errors:
            raise AirflowFailException(
                "[SEV-1] Scoring coverage failure:\n" + "\n".join(errors)
            )

        logger.info(
            "Coverage validation PASSED — %d/%d accounts scored for intent and churn",
            n_active, n_active,
        )

    # ------------------------------------------------------------------
    # Wire up task dependencies
    # ------------------------------------------------------------------

    model_paths     = load_models()
    active_accounts = fetch_active_accounts()
    signal_data     = fetch_signal_data(active_accounts)
    feature_vecs    = compute_features(active_accounts, signal_data)

    intent_results  = score_intent(feature_vecs, model_paths)
    churn_results   = score_churn(feature_vecs, model_paths)

    persist_result  = persist_scores(intent_results, churn_results, feature_vecs)
    validate_coverage(active_accounts, persist_result)


# ---------------------------------------------------------------------------
# Private helpers (module-level so tasks can call them without closure issues)
# ---------------------------------------------------------------------------


def _deserialize_fv(d: dict[str, Any]) -> dict[str, Any]:
    """Convert serialised AccountFeatureVector dict back to constructor kwargs.

    Restores the as_of datetime from ISO string produced by .to_dict().
    """
    from datetime import datetime, timezone

    out = dict(d)
    if isinstance(out.get("as_of"), str):
        out["as_of"] = datetime.fromisoformat(out["as_of"])
        if out["as_of"].tzinfo is None:
            out["as_of"] = out["as_of"].replace(tzinfo=timezone.utc)
    return out


# Register with Airflow
dag_instance = intent_score_refresh_dag()
