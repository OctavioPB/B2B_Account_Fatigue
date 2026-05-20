-- Migration 002: Performance indexes for query-critical columns
-- Idempotent: all CREATE INDEX statements use IF NOT EXISTS.
-- Target p99 API latency < 200ms under 500 concurrent requests (Sprint 10 load test gate).

-- ---------------------------------------------------------------------------
-- accounts table (created by app tenant schemas via Alembic)
-- These indexes are applied to the public schema template; Alembic copies them
-- into each tenant schema on provisioning.
-- ---------------------------------------------------------------------------

-- Primary lookup: every account query is keyed by normalized domain
CREATE INDEX IF NOT EXISTS idx_accounts_domain
    ON accounts (domain);

CREATE INDEX IF NOT EXISTS idx_accounts_is_active_domain
    ON accounts (is_active, domain)
    WHERE is_active = TRUE;

-- Firmographic filters (used in account list with filtering)
CREATE INDEX IF NOT EXISTS idx_accounts_industry
    ON accounts (industry)
    WHERE industry IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_accounts_arr_usd
    ON accounts (arr_usd DESC NULLS LAST)
    WHERE arr_usd IS NOT NULL;

-- ---------------------------------------------------------------------------
-- account_scores (intent + churn scores from Sprint 5 pipeline)
-- ---------------------------------------------------------------------------

-- Latest score lookup per account (ORDER BY computed_at DESC LIMIT 1)
CREATE INDEX IF NOT EXISTS idx_account_scores_domain_computed
    ON account_scores (account_domain, computed_at DESC);

CREATE INDEX IF NOT EXISTS idx_account_scores_score_type_computed
    ON account_scores (score_type, computed_at DESC);

-- Freshness check: find stale accounts (DAG validation + Sev-1 alert)
CREATE INDEX IF NOT EXISTS idx_account_scores_computed_at
    ON account_scores (computed_at DESC);

-- ---------------------------------------------------------------------------
-- account_fatigue_scores (Sprint 6 — 30-min refresh pipeline)
-- ---------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_fatigue_scores_domain_computed
    ON account_fatigue_scores (account_domain, computed_at DESC);

-- Severity-based alert queries (CRITICAL fatigue accounts — NBA dispatcher)
CREATE INDEX IF NOT EXISTS idx_fatigue_scores_severity
    ON account_fatigue_scores (severity, computed_at DESC)
    WHERE severity IN ('HIGH', 'CRITICAL');

-- ---------------------------------------------------------------------------
-- next_best_actions (Sprint 7 — NBA orchestrator)
-- ---------------------------------------------------------------------------

-- v_active_nba view uses DISTINCT ON (account_id) ORDER BY created_at DESC
CREATE INDEX IF NOT EXISTS idx_nba_account_id_active_created
    ON next_best_actions (account_id, is_active, created_at DESC);

-- Active NBA count for coverage validation (Sev-1 check in DAG)
CREATE INDEX IF NOT EXISTS idx_nba_is_active_expires
    ON next_best_actions (is_active, expires_at)
    WHERE is_active = TRUE;

-- Action-type distribution queries (DAG reporting)
CREATE INDEX IF NOT EXISTS idx_nba_action_type_active
    ON next_best_actions (action_type, is_active)
    WHERE is_active = TRUE;

-- ---------------------------------------------------------------------------
-- webhook_delivery_log (Sprint 8 — outbound webhook dispatch)
-- ---------------------------------------------------------------------------

-- Retry sweep: find pending/retrying deliveries
CREATE INDEX IF NOT EXISTS idx_delivery_log_status_created
    ON webhook_delivery_log (status, created_at)
    WHERE status IN ('pending', 'retrying');

-- Per-webhook delivery history (tenant support queries)
CREATE INDEX IF NOT EXISTS idx_delivery_log_webhook_created
    ON webhook_delivery_log (webhook_id, created_at DESC);

-- ---------------------------------------------------------------------------
-- audit_log (Sprint 10 — write-operation audit trail)
-- ---------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_audit_log_tenant_occurred
    ON audit_log (tenant_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_audit_log_occurred_at
    ON audit_log (occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_audit_log_resource_type
    ON audit_log (resource_type, occurred_at DESC);

-- ---------------------------------------------------------------------------
-- committee_members (identity resolution — account-first rollup)
-- ---------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_committee_members_account_domain
    ON committee_members (account_domain);

CREATE INDEX IF NOT EXISTS idx_committee_members_email
    ON committee_members (email);

-- Current-member-only queries (most dashboard queries filter is_current=TRUE)
CREATE INDEX IF NOT EXISTS idx_committee_members_account_current
    ON committee_members (account_domain, is_current)
    WHERE is_current = TRUE;

-- ---------------------------------------------------------------------------
-- account_cooldowns (Sprint 6 — Redis is authoritative; this is audit/fallback)
-- ---------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_account_cooldowns_account_id_active
    ON account_cooldowns (account_id, expires_at)
    WHERE cleared_at IS NULL;

-- ---------------------------------------------------------------------------
-- tenants (Sprint 8 — multi-tenant)
-- Already has idx_tenants_slug and idx_tenants_schema_name from migration 001.
-- Add composite index for plan + active status (admin reporting).
-- ---------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_tenants_plan_active
    ON tenants (plan, is_active)
    WHERE is_active = TRUE;
