-- =============================================================================
-- Sprint 7: Next Best Action (NBA) Table
-- =============================================================================
-- Stores one active NextBestAction per account at any point in time.
-- History is preserved (is_active=FALSE + superseded_by set) to allow
-- auditing, A/B evaluation, and model retraining ground truth.
--
-- Conflict resolution rule: latest action overwrites unless existing is
-- a COOLDOWN or DEAL_REVIEW (these persist until they expire or are manually
-- cleared). The superseded_by FK links the chain.
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- Enum: nba_action_type
-- All seven canonical NBA action types (per CLAUDE.md Section 4.7)
-- ---------------------------------------------------------------------------

CREATE TYPE nba_action_type AS ENUM (
    'COOLDOWN',         -- Pause all outreach; account is fatigued
    'NURTURE',          -- Low-pressure educational content sequence
    'RE_ENGAGE',        -- Personalized re-engagement for declining accounts
    'ACCELERATE',       -- High-intent — escalate cadence and frequency
    'EXEC_ESCALATION',  -- Route to AE/VP for exec-to-exec outreach
    'PRICING_TRIGGER',  -- Surface pricing/ROI content (high intent detected)
    'DEAL_REVIEW'       -- Internal flag — churn risk critical, human review required
);

-- ---------------------------------------------------------------------------
-- next_best_actions
-- One row per recommended action per account per orchestration run.
-- Never delete rows — use is_active=FALSE + superseded_by to deactivate.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS next_best_actions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id      UUID NOT NULL REFERENCES accounts (id) ON DELETE CASCADE,
    account_domain  VARCHAR(255) NOT NULL,

    -- The recommended action
    action_type     nba_action_type NOT NULL,

    -- Priority: 1=highest (COOLDOWN), 7=lowest (NURTURE)
    -- Used for conflict resolution between simultaneous recommendations
    priority        SMALLINT NOT NULL CHECK (priority BETWEEN 1 AND 7),

    -- Human-readable explanation of why this action was chosen
    rationale       TEXT NOT NULL,

    -- Which signals triggered this action (array of "signal=value" strings)
    triggered_by    JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- Score snapshots at the time this action was generated (for audit/training)
    fatigue_score   NUMERIC(5, 2),
    intent_score    NUMERIC(5, 2),
    churn_probability NUMERIC(4, 3),

    -- Lifecycle
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,

    -- UTC timestamp when this NBA expires (action becomes stale)
    expires_at      TIMESTAMP WITH TIME ZONE NOT NULL,

    -- UTC timestamp when this NBA was created
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Which newer action superseded this one (NULL while is_active=TRUE)
    superseded_by   UUID REFERENCES next_best_actions (id)
);

CREATE INDEX idx_nba_account_id     ON next_best_actions (account_id);
CREATE INDEX idx_nba_domain         ON next_best_actions (account_domain);
CREATE INDEX idx_nba_action_type    ON next_best_actions (action_type);
CREATE INDEX idx_nba_created_at     ON next_best_actions (created_at DESC);

-- Fast lookup of active NBA per account (the common read path)
CREATE INDEX idx_nba_active ON next_best_actions (account_id, is_active, expires_at)
    WHERE is_active = TRUE;

-- ---------------------------------------------------------------------------
-- Convenience view: current (active, non-expired) NBA per account
-- ---------------------------------------------------------------------------

CREATE VIEW v_active_nba AS
SELECT DISTINCT ON (account_id)
    id,
    account_id,
    account_domain,
    action_type,
    priority,
    rationale,
    triggered_by,
    fatigue_score,
    intent_score,
    churn_probability,
    expires_at,
    created_at
FROM next_best_actions
WHERE is_active  = TRUE
  AND expires_at > NOW()
ORDER BY account_id, created_at DESC;

COMMIT;
