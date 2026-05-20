-- =============================================================================
-- Sprint 6: Account Fatigue Score Tables
-- =============================================================================
-- Stores time-series history of AccountFatigueScore and the audit trail for
-- Redis-backed ActionCooldowns. The Redis keys are the live enforcement layer;
-- this table provides durability, trend analysis, and compliance auditing.
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- Enum: fatigue_severity
-- Mirrors ChurnRiskLevel values but is semantically distinct — describes the
-- cognitive-load tier of a buying committee, not deal-loss probability.
-- ---------------------------------------------------------------------------

CREATE TYPE fatigue_severity AS ENUM ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL');

-- ---------------------------------------------------------------------------
-- account_fatigue_scores
-- One row per account per computation run (append-only, never updated).
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS account_fatigue_scores (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id          UUID NOT NULL REFERENCES accounts (id) ON DELETE CASCADE,
    account_domain      VARCHAR(255) NOT NULL,

    -- Composite fatigue score: 0–100 (higher = more fatigued)
    score               NUMERIC(5, 2) NOT NULL
                            CHECK (score >= 0 AND score <= 100),

    -- Categorical severity tier derived from score thresholds
    severity            fatigue_severity NOT NULL,

    -- Account segment used for weight selection (SMB | MID_MARKET | ENTERPRISE | DEFAULT)
    account_segment     VARCHAR(50) NOT NULL DEFAULT 'DEFAULT',

    -- Per-component breakdown (name, score, weight, breakdown dict per component)
    components          JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- Counts driving this score (summary for fast dashboard queries)
    outreach_7d         INTEGER NOT NULL DEFAULT 0,
    outreach_30d        INTEGER NOT NULL DEFAULT 0,
    negative_signals_30d INTEGER NOT NULL DEFAULT 0,
    days_since_meaningful_reply NUMERIC(6, 1),

    -- When this score was computed (UTC)
    computed_at         TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_fatigue_scores_account_id ON account_fatigue_scores (account_id);
CREATE INDEX idx_fatigue_scores_domain     ON account_fatigue_scores (account_domain);
CREATE INDEX idx_fatigue_scores_time       ON account_fatigue_scores (computed_at DESC);
CREATE INDEX idx_fatigue_scores_severity   ON account_fatigue_scores (severity, computed_at DESC);

-- Fast retrieval of latest fatigue score per account
CREATE INDEX idx_fatigue_scores_latest ON account_fatigue_scores (account_id, computed_at DESC);

-- ---------------------------------------------------------------------------
-- account_cooldowns
-- Audit trail for Redis-backed ActionCooldown entries.
-- Redis is the live enforcement layer; this table provides durability and
-- compliance auditing. Rows are never deleted — cleared_at is set when a
-- cooldown expires or is manually lifted.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS account_cooldowns (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- 'account' | 'member'
    entity_type     VARCHAR(20)  NOT NULL CHECK (entity_type IN ('account', 'member')),
    entity_id       UUID         NOT NULL,

    -- Domain for fast account-scoped queries (member cooldowns carry account domain too)
    account_domain  VARCHAR(255) NOT NULL,

    -- Severity at the time the cooldown was set (drives TTL)
    severity        fatigue_severity NOT NULL,

    -- Fatigue score that triggered this cooldown
    trigger_score   NUMERIC(5, 2),

    -- TTL-derived expiry (UTC); set to now() + TTL at creation time
    expires_at      TIMESTAMP WITH TIME ZONE NOT NULL,

    -- When the cooldown was set (UTC)
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- When the cooldown was lifted (NULL = still active or expired naturally)
    cleared_at      TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_cooldowns_entity        ON account_cooldowns (entity_type, entity_id);
CREATE INDEX idx_cooldowns_domain        ON account_cooldowns (account_domain);
CREATE INDEX idx_cooldowns_expires_at    ON account_cooldowns (expires_at);
CREATE INDEX idx_cooldowns_active        ON account_cooldowns (entity_id, expires_at)
    WHERE cleared_at IS NULL;

-- ---------------------------------------------------------------------------
-- Convenience view: latest fatigue score per account
-- ---------------------------------------------------------------------------

CREATE VIEW v_latest_account_fatigue AS
SELECT DISTINCT ON (account_id)
    id,
    account_id,
    account_domain,
    score,
    severity,
    account_segment,
    components,
    outreach_7d,
    outreach_30d,
    negative_signals_30d,
    days_since_meaningful_reply,
    computed_at
FROM account_fatigue_scores
ORDER BY account_id, computed_at DESC;

-- ---------------------------------------------------------------------------
-- Convenience view: active cooldowns (not expired, not manually cleared)
-- ---------------------------------------------------------------------------

CREATE VIEW v_active_cooldowns AS
SELECT
    id,
    entity_type,
    entity_id,
    account_domain,
    severity,
    trigger_score,
    expires_at,
    created_at,
    EXTRACT(EPOCH FROM (expires_at - NOW()))::INTEGER AS remaining_seconds
FROM account_cooldowns
WHERE cleared_at IS NULL
  AND expires_at > NOW();

COMMIT;
