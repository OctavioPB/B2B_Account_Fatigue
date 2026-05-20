"""Airflow DAG: dag_fatigue_score_refresh

Runs every 30 minutes to recompute AccountFatigueScore for every active
account, persist results to account_fatigue_scores, and synchronise
ActionCooldown locks in Redis.

Pipeline steps (TaskFlow API):
  1. fetch_active_accounts    — query dim_account for all active accounts with
                                segment classification (ENTERPRISE/MID_MARKET/SMB)
  2. fetch_outreach_data      — load 30-day outreach history from raw_email_engagements
                                grouped by (account_domain, member_id, channel, sent_date)
  3. compute_fatigue_scores   — FatigueScoreEngine.compute() for every account
  4. persist_fatigue_scores   — bulk-insert into account_fatigue_scores (append-only)
  5. apply_cooldowns          — set/clear Redis cooldown locks via ActionCooldownEngine
  6. audit_cooldowns          — write cooldown audit rows to account_cooldowns table
  7. validate_coverage        — assert 100% of active accounts have a fresh score;
                                raise AirflowFailException (Sev-1) on any gap
  8. report_critical_accounts — log accounts in CRITICAL tier for human review

CRITICAL fatigue accounts log to the DAG's task log with prefix [CRITICAL-FATIGUE]
and are surfaced to the NBA orchestrator via the account_fatigue_scores table.

Environment variables:
    DATABASE_URL  — asyncpg-compatible PostgreSQL DSN
    REDIS_URL     — Redis DSN (redis://host:port/db)
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
_REDIS_URL     = os.getenv("REDIS_URL", "redis://localhost:6379/0")

_OUTREACH_LOOKBACK_DAYS = 30

# ARR band → segment mapping for weight selection in FatigueScoreEngine
_ARR_TO_SEGMENT: dict[str, str] = {
    "<$1M":    "SMB",
    "$1M-$5M": "SMB",
    "$5M-$10M": "MID_MARKET",
    "$10M-$50M": "ENTERPRISE",
    "$50M+":   "ENTERPRISE",
    "$100M+":  "ENTERPRISE",
}

_DEFAULT_ARGS: dict[str, Any] = {
    "owner": "harmoni-ml",
    "retries": 2,
    "retry_delay": timedelta(minutes=3),
    "email_on_failure": False,
}


# ---------------------------------------------------------------------------
# DAG definition
# ---------------------------------------------------------------------------


@dag(
    dag_id="dag_fatigue_score_refresh",
    description="30-min Account Fatigue Score refresh + Redis cooldown synchronisation",
    schedule_interval="*/30 * * * *",
    start_date=days_ago(1),
    catchup=False,
    max_active_runs=1,
    default_args=_DEFAULT_ARGS,
    tags=["scoring", "fatigue", "cooldown"],
)
def fatigue_score_refresh_dag() -> None:

    # ------------------------------------------------------------------
    # Task 1: Fetch active accounts with segment info
    # ------------------------------------------------------------------

    @task()
    def fetch_active_accounts() -> list[dict[str, Any]]:
        """Query dim_account for active accounts with segment classification.

        Returns list of dicts:
            {account_id, account_domain, arr_band, account_segment}
        """
        import asyncio
        import asyncpg

        query = """
            SELECT
                id              AS account_id,
                domain          AS account_domain,
                arr_band
            FROM dim_account
            WHERE dbt_valid_to IS NULL   -- current SCD row
              AND is_active     = TRUE
            ORDER BY domain
        """

        async def _fetch() -> list[dict]:
            conn = await asyncpg.connect(_DATABASE_URL)
            try:
                rows = await conn.fetch(query)
                return [dict(r) for r in rows]
            finally:
                await conn.close()

        accounts = asyncio.get_event_loop().run_until_complete(_fetch())

        # Classify segment from ARR band
        for acct in accounts:
            arr_band = acct.get("arr_band") or ""
            acct["account_segment"] = _ARR_TO_SEGMENT.get(arr_band, "DEFAULT")

        logger.info("Fetched %d active accounts for fatigue scoring", len(accounts))
        return accounts

    # ------------------------------------------------------------------
    # Task 2: Fetch outreach data for all active accounts
    # ------------------------------------------------------------------

    @task()
    def fetch_outreach_data(accounts: list[dict[str, Any]]) -> dict[str, list[dict]]:
        """Load 30-day outreach history from raw_email_engagements.

        Returns dict keyed by account_domain with list of daily outreach summary dicts.
        """
        import asyncio
        import asyncpg

        if not accounts:
            return {}

        domains = [a["account_domain"] for a in accounts]
        cutoff  = datetime.now(timezone.utc) - timedelta(days=_OUTREACH_LOOKBACK_DAYS)

        query = """
            SELECT
                a.domain                    AS account_domain,
                e.member_id,
                'EMAIL'                     AS channel,
                DATE_TRUNC('day', e.sent_at)::TIMESTAMPTZ AS sent_date,
                COUNT(*)                    AS sent_count,
                SUM(CASE WHEN e.event_type = 'OPEN'        THEN 1 ELSE 0 END) AS opened_count,
                SUM(CASE WHEN e.event_type = 'CLICK'       THEN 1 ELSE 0 END) AS clicked_count,
                SUM(CASE WHEN e.event_type = 'REPLY'       THEN 1 ELSE 0 END) AS replied_count,
                SUM(CASE WHEN e.event_type = 'REPLY' AND e.is_meaningful THEN 1 ELSE 0 END)
                                                                               AS meaningful_reply_count,
                SUM(CASE WHEN e.event_type = 'BOUNCE'      THEN 1 ELSE 0 END) AS bounced_count,
                SUM(CASE WHEN e.event_type = 'UNSUBSCRIBE' THEN 1 ELSE 0 END) AS unsubscribed_count,
                SUM(CASE WHEN e.event_type = 'SPAM_REPORT' THEN 1 ELSE 0 END) AS spam_reported_count
            FROM raw_email_engagements e
            JOIN accounts a ON a.id = e.account_id
            WHERE a.domain   = ANY($1)
              AND e.sent_at >= $2
            GROUP BY a.domain, e.member_id, DATE_TRUNC('day', e.sent_at)
        """

        async def _fetch() -> list[dict]:
            conn = await asyncpg.connect(_DATABASE_URL)
            try:
                rows = await conn.fetch(query, domains, cutoff)
                return [dict(r) for r in rows]
            finally:
                await conn.close()

        raw_rows = asyncio.get_event_loop().run_until_complete(_fetch())

        by_domain: dict[str, list[dict]] = {}
        for row in raw_rows:
            domain = row["account_domain"]
            by_domain.setdefault(domain, []).append(row)

        logger.info(
            "Fetched %d outreach rows across %d domains",
            len(raw_rows), len(by_domain),
        )
        return by_domain

    # ------------------------------------------------------------------
    # Task 3: Compute fatigue scores
    # ------------------------------------------------------------------

    @task()
    def compute_fatigue_scores(
        accounts: list[dict[str, Any]],
        outreach_by_domain: dict[str, list[dict]],
    ) -> list[dict[str, Any]]:
        """Run FatigueScoreEngine.compute() for every active account.

        Returns list of serialised AccountFatigueScore dicts.
        """
        from scoring.fatigue.engine import FatigueScoreEngine
        from scoring.models import OutreachDaySummary

        engine = FatigueScoreEngine()
        as_of  = datetime.now(timezone.utc)
        results = []

        for acct in accounts:
            domain   = acct["account_domain"]
            raw_rows = outreach_by_domain.get(domain, [])

            outreach_rows = [
                OutreachDaySummary(
                    sent_date=row["sent_date"] if isinstance(row["sent_date"], datetime)
                              else datetime.fromisoformat(str(row["sent_date"])).replace(tzinfo=timezone.utc),
                    member_id=row["member_id"],
                    channel=row.get("channel", "EMAIL"),
                    sent_count=int(row.get("sent_count", 0)),
                    opened_count=int(row.get("opened_count", 0)),
                    clicked_count=int(row.get("clicked_count", 0)),
                    replied_count=int(row.get("replied_count", 0)),
                    meaningful_reply_count=int(row.get("meaningful_reply_count", 0)),
                    bounced_count=int(row.get("bounced_count", 0)),
                    unsubscribed_count=int(row.get("unsubscribed_count", 0)),
                    spam_reported_count=int(row.get("spam_reported_count", 0)),
                )
                for row in raw_rows
            ]

            score = engine.compute(
                account_id=acct["account_id"],
                account_domain=domain,
                outreach_rows=outreach_rows,
                account_segment=acct.get("account_segment", "DEFAULT"),
                as_of=as_of,
            )
            results.append(score.to_dict())

        n_critical = sum(1 for r in results if r["severity"] == "CRITICAL")
        n_high     = sum(1 for r in results if r["severity"] == "HIGH")
        logger.info(
            "Fatigue scores computed: %d accounts (CRITICAL=%d, HIGH=%d, avg=%.1f)",
            len(results), n_critical, n_high,
            sum(r["score"] for r in results) / max(len(results), 1),
        )
        return results

    # ------------------------------------------------------------------
    # Task 4: Persist fatigue scores (append-only)
    # ------------------------------------------------------------------

    @task()
    def persist_fatigue_scores(
        accounts: list[dict[str, Any]],
        fatigue_scores: list[dict[str, Any]],
    ) -> int:
        """Bulk-insert fatigue scores into account_fatigue_scores (append-only).

        Never updates existing rows — historical truth is inviolable.

        Returns count of rows inserted.
        """
        import asyncio
        import json
        import asyncpg

        account_id_by_domain = {a["account_domain"]: a["account_id"] for a in accounts}

        insert_sql = """
            INSERT INTO account_fatigue_scores (
                account_id, account_domain, score, severity, account_segment,
                components, outreach_7d, outreach_30d, negative_signals_30d,
                days_since_meaningful_reply, computed_at
            ) VALUES ($1, $2, $3, $4::fatigue_severity, $5, $6::jsonb, $7, $8, $9, $10, $11)
        """

        def _make_row(s: dict) -> tuple:
            domain = s["account_domain"]
            account_id = account_id_by_domain.get(domain)

            # Extract summary stats from component breakdowns
            freq_comp = next((c for c in s["components"] if c["name"] == "outreach_frequency"), None)
            neg_comp  = next((c for c in s["components"] if c["name"] == "negative_signal"), None)
            rec_comp  = next((c for c in s["components"] if c["name"] == "recency"), None)

            outreach_7d  = int(freq_comp["breakdown"].get("sent_7d", 0)) if freq_comp else 0
            outreach_30d = int(freq_comp["breakdown"].get("sent_14d", 0)) if freq_comp else 0
            neg_signals  = int(
                (neg_comp["breakdown"].get("unsubscribed_30d", 0) or 0)
                + (neg_comp["breakdown"].get("spam_reported_30d", 0) or 0)
                + (neg_comp["breakdown"].get("bounced_30d", 0) or 0)
            ) if neg_comp else 0
            days_since_reply = rec_comp["breakdown"].get("days_since_meaningful_reply") if rec_comp else None

            return (
                account_id,
                domain,
                float(s["score"]),
                s["severity"],
                s.get("account_segment", "DEFAULT"),
                json.dumps(s["components"]),
                outreach_7d,
                outreach_30d,
                neg_signals,
                float(days_since_reply) if days_since_reply is not None else None,
                datetime.fromisoformat(s["computed_at"]),
            )

        async def _insert() -> int:
            conn = await asyncpg.connect(_DATABASE_URL)
            try:
                rows = [_make_row(s) for s in fatigue_scores]
                await conn.executemany(insert_sql, rows)
                return len(rows)
            finally:
                await conn.close()

        n = asyncio.get_event_loop().run_until_complete(_insert())
        logger.info("Persisted %d fatigue score rows", n)
        return n

    # ------------------------------------------------------------------
    # Task 5: Apply Redis cooldowns
    # ------------------------------------------------------------------

    @task()
    def apply_cooldowns(
        accounts: list[dict[str, Any]],
        fatigue_scores: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Set or clear Redis cooldown locks for each account.

        Returns list of cooldown action dicts for the audit task.
        Each dict: {account_id, account_domain, action, severity, ttl}
        """
        import redis as redis_lib
        from scoring.fatigue.cooldown import ActionCooldownEngine
        from scoring.models import AccountFatigueScore, FatigueSeverity

        r = redis_lib.from_url(_REDIS_URL, decode_responses=True)
        engine = ActionCooldownEngine(r)

        score_by_account = {s["account_id"]: s for s in fatigue_scores if s.get("account_id")}
        account_id_by_domain = {a["account_domain"]: a["account_id"] for a in accounts}

        # Rebuild AccountFatigueScore objects for apply_fatigue_score
        score_objects: dict[str, AccountFatigueScore] = {}
        for s in fatigue_scores:
            domain = s["account_domain"]
            acct_id = account_id_by_domain.get(domain)
            if acct_id:
                score_objects[acct_id] = AccountFatigueScore(
                    account_id=acct_id,
                    account_domain=domain,
                    score=float(s["score"]),
                    severity=FatigueSeverity(s["severity"]),
                    account_segment=s.get("account_segment", "DEFAULT"),
                )

        cooldown_actions = []
        for acct in accounts:
            acct_id = acct["account_id"]
            score_obj = score_objects.get(acct_id)
            if score_obj is None:
                continue

            action_result = engine.apply_fatigue_score(acct_id, score_obj)
            cooldown_actions.append({
                "account_id":     acct_id,
                "account_domain": acct["account_domain"],
                "action":         action_result["action"],
                "severity":       action_result.get("severity"),
                "ttl":            action_result.get("ttl"),
            })

        n_set     = sum(1 for a in cooldown_actions if a["action"] == "set")
        n_cleared = sum(1 for a in cooldown_actions if a["action"] == "cleared")
        logger.info(
            "Cooldown sync complete: %d set, %d cleared, %d no_change",
            n_set, n_cleared, len(cooldown_actions) - n_set - n_cleared,
        )
        return cooldown_actions

    # ------------------------------------------------------------------
    # Task 6: Audit cooldown changes
    # ------------------------------------------------------------------

    @task()
    def audit_cooldowns(
        cooldown_actions: list[dict[str, Any]],
        fatigue_scores: list[dict[str, Any]],
    ) -> None:
        """Write cooldown audit rows to account_cooldowns for compliance.

        Only inserts rows for SET actions (new locks). CLEARED and no_change
        actions update the cleared_at column on the most recent open row.
        """
        import asyncio
        import asyncpg
        from datetime import timedelta

        score_by_domain = {s["account_domain"]: s for s in fatigue_scores}

        set_actions     = [a for a in cooldown_actions if a["action"] == "set"]
        cleared_actions = [a for a in cooldown_actions if a["action"] == "cleared"]

        insert_sql = """
            INSERT INTO account_cooldowns (
                entity_type, entity_id, account_domain, severity,
                trigger_score, expires_at
            ) VALUES ($1, $2, $3, $4::fatigue_severity, $5, $6)
        """

        clear_sql = """
            UPDATE account_cooldowns
            SET cleared_at = NOW()
            WHERE entity_type = 'account'
              AND entity_id    = $1::uuid
              AND cleared_at  IS NULL
              AND expires_at   > NOW()
        """

        async def _audit() -> None:
            conn = await asyncpg.connect(_DATABASE_URL)
            try:
                async with conn.transaction():
                    if set_actions:
                        now = datetime.now(timezone.utc)
                        from scoring.fatigue.cooldown import COOLDOWN_TTL_SECONDS
                        from scoring.models import FatigueSeverity

                        insert_rows = []
                        for a in set_actions:
                            severity = FatigueSeverity(a["severity"])
                            ttl      = COOLDOWN_TTL_SECONDS[severity]
                            trigger_score = float(score_by_domain.get(a["account_domain"], {}).get("score", 0))
                            insert_rows.append((
                                "account",
                                a["account_id"],
                                a["account_domain"],
                                a["severity"],
                                trigger_score,
                                now + timedelta(seconds=ttl),
                            ))
                        await conn.executemany(insert_sql, insert_rows)

                    for a in cleared_actions:
                        await conn.execute(clear_sql, a["account_id"])
            finally:
                await conn.close()

        asyncio.get_event_loop().run_until_complete(_audit())
        logger.info(
            "Cooldown audit: %d rows inserted, %d rows cleared",
            len(set_actions), len(cleared_actions),
        )

    # ------------------------------------------------------------------
    # Task 7: Validate coverage
    # ------------------------------------------------------------------

    @task()
    def validate_coverage(
        accounts: list[dict[str, Any]],
        n_persisted: int,
    ) -> None:
        """Assert 100% of active accounts received a fatigue score.

        Raises AirflowFailException (Sev-1) if count mismatch detected.
        """
        n_active = len(accounts)
        if n_persisted < n_active:
            raise AirflowFailException(
                f"[SEV-1] Fatigue scoring coverage gap: "
                f"{n_active - n_persisted} accounts missing scores "
                f"(expected {n_active}, persisted {n_persisted})"
            )
        logger.info(
            "Coverage validation PASSED — %d/%d accounts scored",
            n_active, n_active,
        )

    # ------------------------------------------------------------------
    # Task 8: Report CRITICAL accounts
    # ------------------------------------------------------------------

    @task()
    def report_critical_accounts(fatigue_scores: list[dict[str, Any]]) -> None:
        """Log all CRITICAL-tier accounts for immediate human review.

        These accounts have crossed the 80-point threshold and require
        the NBA orchestrator to emit EXEC_ESCALATION or DEAL_REVIEW actions.
        """
        critical = [s for s in fatigue_scores if s["severity"] == "CRITICAL"]
        high     = [s for s in fatigue_scores if s["severity"] == "HIGH"]

        for s in critical:
            logger.warning(
                "[CRITICAL-FATIGUE] account=%s score=%.1f — immediate human review required",
                s["account_domain"], s["score"],
            )

        if critical or high:
            logger.info(
                "Fatigue tier summary: CRITICAL=%d HIGH=%d MEDIUM=%d LOW=%d",
                len(critical),
                len(high),
                sum(1 for s in fatigue_scores if s["severity"] == "MEDIUM"),
                sum(1 for s in fatigue_scores if s["severity"] == "LOW"),
            )
        else:
            logger.info("No HIGH or CRITICAL fatigue accounts this run")

    # ------------------------------------------------------------------
    # Wire up task dependencies
    # ------------------------------------------------------------------

    active_accounts    = fetch_active_accounts()
    outreach_data      = fetch_outreach_data(active_accounts)
    scores             = compute_fatigue_scores(active_accounts, outreach_data)
    n_persisted        = persist_fatigue_scores(active_accounts, scores)
    cooldown_actions   = apply_cooldowns(active_accounts, scores)

    audit_cooldowns(cooldown_actions, scores)
    validate_coverage(active_accounts, n_persisted)
    report_critical_accounts(scores)


# Register with Airflow
dag_instance = fatigue_score_refresh_dag()
