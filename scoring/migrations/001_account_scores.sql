-- =============================================================================
-- Sprint 5: Account Scores Table
-- =============================================================================
-- Stores time-series history of IntentScore and ChurnPrediction for every
-- active account. Never overwrite â€” append new rows so the full score history
-- is preserved for trend analysis and model evaluation.
-- =============================================================================

BEGIN;

DO $$ BEGIN
    CREATE TYPE score_type AS ENUM ('INTENT', 'CHURN');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE churn_risk_level AS ENUM ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ---------------------------------------------------------------------------
-- account_scores
-- One row per account per score type per computation run.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS account_scores (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id          UUID NOT NULL REFERENCES accounts (id) ON DELETE CASCADE,
    account_domain      VARCHAR(255) NOT NULL,
    score_type          score_type NOT NULL,

    -- For INTENT: 0.0â€“100.0 (higher = stronger buying intent)
    -- For CHURN:  0.0â€“1.0   (probability of abandonment within 30 days)
    score               NUMERIC(6, 2) NOT NULL,

    -- Model confidence in this prediction (0.0â€“1.0)
    confidence          NUMERIC(4, 3),

    -- CHURN only: risk tier derived from probability thresholds
    risk_level          churn_risk_level,

    -- Human-readable breakdown of the top contributing signals
    signal_breakdown    JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- Feature vector snapshot (for model diagnostics and retraining)
    feature_vector      JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- Model lineage
    model_version       VARCHAR(50) NOT NULL,

    -- When this score was computed (UTC)
    computed_at         TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Prediction window (CHURN only: 30 days)
    prediction_window_days INTEGER DEFAULT 30
);

CREATE INDEX IF NOT EXISTS idx_account_scores_account_id  ON account_scores (account_id);
CREATE INDEX IF NOT EXISTS idx_account_scores_domain      ON account_scores (account_domain);
CREATE INDEX IF NOT EXISTS idx_account_scores_type_time   ON account_scores (score_type, computed_at DESC);
CREATE INDEX IF NOT EXISTS idx_account_scores_computed_at ON account_scores (computed_at DESC);

-- Partial index: fast retrieval of latest INTENT score per account
CREATE INDEX IF NOT EXISTS idx_account_scores_latest_intent ON account_scores (account_id, computed_at DESC)
    WHERE score_type = 'INTENT';

-- Partial index: fast retrieval of latest CHURN score per account
CREATE INDEX IF NOT EXISTS idx_account_scores_latest_churn ON account_scores (account_id, computed_at DESC)
    WHERE score_type = 'CHURN';

-- ---------------------------------------------------------------------------
-- Convenience view: latest score per account per type
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW v_latest_account_scores AS
SELECT DISTINCT ON (account_id, score_type)
    id,
    account_id,
    account_domain,
    score_type,
    score,
    confidence,
    risk_level,
    signal_breakdown,
    model_version,
    computed_at
FROM account_scores
ORDER BY account_id, score_type, computed_at DESC;

COMMIT;
