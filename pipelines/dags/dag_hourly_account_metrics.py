"""Airflow DAG: dag_hourly_account_metrics

Runs every hour to:
  1. Run dbt staging views (fast — PostgreSQL views, no data movement)
  2. Run dbt snapshots (SCD Type 2 on accounts + committee_members)
  3. Run dbt intermediate incremental models
  4. Run dbt dimension views (PostgreSQL)
  5. Run dbt singular tests (including SCD immutability checks)
  6. Run dbt fact models on ClickHouse target
  7. Validate ClickHouse write latency

Uses Airflow TaskFlow API (@task decorator) per CLAUDE.md Section 7.
All tasks use subprocess calls to the dbt CLI for maximum compatibility
with dbt Cloud and local dev environments.

Environment variables consumed:
    DBT_PROJECT_DIR   — absolute path to pipelines/dbt/
    DBT_PROFILES_DIR  — directory containing profiles.yml
    DBT_TARGET        — dbt profile target (default: dev)
    DBT_CH_TARGET     — ClickHouse profile target (default: clickhouse)
"""

from __future__ import annotations

import logging
import os
import subprocess
from datetime import datetime, timedelta, timezone
from typing import Any

from airflow.decorators import dag, task
from airflow.exceptions import AirflowFailException
from airflow.models import Variable
from airflow.utils.dates import days_ago

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DAG-level constants
# ---------------------------------------------------------------------------

_DBT_PROJECT_DIR = os.getenv(
    "DBT_PROJECT_DIR",
    os.path.join(os.path.dirname(__file__), "..", "dbt"),
)
_DBT_PROFILES_DIR = os.getenv("DBT_PROFILES_DIR", os.path.expanduser("~/.dbt"))
_DBT_TARGET = os.getenv("DBT_TARGET", "dev")
_DBT_CH_TARGET = os.getenv("DBT_CH_TARGET", "clickhouse")

_DEFAULT_ARGS: dict[str, Any] = {
    "owner": "data-engineering",
    "depends_on_past": False,
    "email_on_failure": True,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "execution_timeout": timedelta(minutes=45),
}


# ---------------------------------------------------------------------------
# dbt CLI helper
# ---------------------------------------------------------------------------


def _run_dbt(
    *args: str,
    target: str = _DBT_TARGET,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a dbt CLI command and return the CompletedProcess.

    Args:
        *args:   dbt subcommand and flags (e.g. "run", "--select", "staging.*").
        target:  dbt profile target.
        check:   If True, raise AirflowFailException on non-zero exit code.

    Returns:
        CompletedProcess with stdout/stderr captured.
    """
    cmd = [
        "dbt",
        *args,
        "--project-dir", _DBT_PROJECT_DIR,
        "--profiles-dir", _DBT_PROFILES_DIR,
        "--target", target,
        "--no-use-colors",
    ]
    logger.info("Running: %s", " ".join(cmd))
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=_DBT_PROJECT_DIR,
    )
    if result.stdout:
        logger.info("dbt stdout:\n%s", result.stdout[-4000:])
    if result.stderr:
        logger.warning("dbt stderr:\n%s", result.stderr[-2000:])

    if check and result.returncode != 0:
        raise AirflowFailException(
            f"dbt command failed (exit {result.returncode}): {' '.join(args)}\n"
            f"stderr: {result.stderr[-1000:]}"
        )
    return result


# ---------------------------------------------------------------------------
# DAG definition
# ---------------------------------------------------------------------------


@dag(
    dag_id="dag_hourly_account_metrics",
    description=(
        "Hourly account metrics pipeline: dbt snapshots (SCD Type 2), "
        "intermediate signal aggregation, dimension refresh, and ClickHouse "
        "fact table writes."
    ),
    schedule_interval="@hourly",
    start_date=days_ago(1),
    catchup=False,
    max_active_runs=1,
    default_args=_DEFAULT_ARGS,
    tags=["harmoni", "dbt", "data-warehouse", "sprint4"],
)
def dag_hourly_account_metrics() -> None:

    # ------------------------------------------------------------------
    # Task 1: Run dbt staging models (PostgreSQL views — idempotent, fast)
    # ------------------------------------------------------------------

    @task(task_id="dbt_run_staging")
    def run_staging() -> dict[str, Any]:
        """Refresh dbt staging views on PostgreSQL.

        Views are re-created on every dbt run; no incremental logic.
        Errors here indicate schema drift in source tables.
        """
        result = _run_dbt("run", "--select", "staging.*")
        return {"returncode": result.returncode, "task": "staging"}

    # ------------------------------------------------------------------
    # Task 2: Run SCD Type 2 snapshots
    # ------------------------------------------------------------------

    @task(task_id="dbt_run_snapshots")
    def run_snapshots(staging_result: dict[str, Any]) -> dict[str, Any]:
        """Execute dbt snapshots for accounts and committee members.

        Detects changes via updated_at timestamp and inserts new snapshot rows.
        NEVER modifies existing rows — enforced by assert_no_scd_mutations test.
        """
        result = _run_dbt("snapshot")
        return {"returncode": result.returncode, "task": "snapshots"}

    # ------------------------------------------------------------------
    # Task 3: Run intermediate incremental models (PostgreSQL)
    # ------------------------------------------------------------------

    @task(task_id="dbt_run_intermediate")
    def run_intermediate(snapshot_result: dict[str, Any]) -> dict[str, Any]:
        """Run int_account_signals and int_committee_composition (incremental)."""
        result = _run_dbt("run", "--select", "intermediate.*")
        return {"returncode": result.returncode, "task": "intermediate"}

    # ------------------------------------------------------------------
    # Task 4: Refresh dimension views (PostgreSQL)
    # ------------------------------------------------------------------

    @task(task_id="dbt_run_dimensions")
    def run_dimensions(intermediate_result: dict[str, Any]) -> dict[str, Any]:
        """Refresh dim_account and dim_committee_member views."""
        result = _run_dbt("run", "--select", "marts.dimensions.*")
        return {"returncode": result.returncode, "task": "dimensions"}

    # ------------------------------------------------------------------
    # Task 5: Run dbt tests (including SCD immutability singular tests)
    # ------------------------------------------------------------------

    @task(task_id="dbt_test_scd_and_schemas")
    def run_tests(dimension_result: dict[str, Any]) -> dict[str, Any]:
        """Run all dbt tests including custom SCD immutability assertions.

        A failure here is Sev-1 if it is assert_no_scd_mutations.
        Other test failures are logged and re-raised.
        """
        result = _run_dbt(
            "test",
            "--select",
            "staging.* intermediate.* snapshots.* marts.dimensions.*",
            check=False,  # capture failure details before raising
        )
        if result.returncode != 0:
            # Distinguish SCD test failures (critical) from schema test failures
            if "assert_no_scd_mutations" in result.stdout:
                raise AirflowFailException(
                    "CRITICAL: SCD immutability test failed — historical snapshot "
                    "rows have been mutated. Investigate immediately (ADR 0002)."
                )
            raise AirflowFailException(
                f"dbt test failures detected. See logs for details."
            )
        return {"returncode": result.returncode, "task": "tests"}

    # ------------------------------------------------------------------
    # Task 6: Write fact models to ClickHouse
    # ------------------------------------------------------------------

    @task(task_id="dbt_run_facts_clickhouse")
    def run_facts_clickhouse(test_result: dict[str, Any]) -> dict[str, Any]:
        """Run fct_account_signal_hourly and fct_committee_engagement on ClickHouse.

        Uses the 'clickhouse' dbt target (dbt-clickhouse adapter).
        Incremental: only processes signals from the last N days watermark.
        """
        result = _run_dbt(
            "run",
            "--select", "marts.facts.*",
            target=_DBT_CH_TARGET,
        )
        return {"returncode": result.returncode, "task": "facts_clickhouse"}

    # ------------------------------------------------------------------
    # Task 7: Validate ClickHouse freshness
    # ------------------------------------------------------------------

    @task(task_id="validate_clickhouse_freshness")
    def validate_clickhouse_freshness(facts_result: dict[str, Any]) -> dict[str, Any]:
        """Assert ClickHouse fact tables were refreshed within the last 2 hours.

        Runs dbt source freshness check against the ClickHouse target.
        Alerts on staleness without failing the DAG (warn severity).
        """
        result = _run_dbt(
            "source", "freshness",
            "--select", "marts.facts.*",
            target=_DBT_CH_TARGET,
            check=False,
        )
        if result.returncode != 0:
            logger.warning(
                "ClickHouse freshness check warned or failed. "
                "Fact tables may be stale. returncode=%d",
                result.returncode,
            )
        return {"returncode": result.returncode, "task": "freshness_check"}

    # ------------------------------------------------------------------
    # Wire up task dependencies
    # ------------------------------------------------------------------

    staging    = run_staging()
    snapshots  = run_snapshots(staging)
    intermed   = run_intermediate(snapshots)
    dimensions = run_dimensions(intermed)
    tests      = run_tests(dimensions)
    facts_ch   = run_facts_clickhouse(tests)
    _          = validate_clickhouse_freshness(facts_ch)


# Instantiate the DAG
dag_hourly_account_metrics()
