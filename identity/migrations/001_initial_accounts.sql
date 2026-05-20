-- =============================================================================
-- Sprint 3: Draft Account Identity Schema
-- =============================================================================
-- SPRINT 4 NOTE: SCD Type 2 snapshot columns (dbt_valid_from, dbt_valid_to,
-- is_current, dbt_scd_id) will be added by dbt snapshot blocks in Sprint 4.
-- Do NOT add those columns here — dbt manages them.
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- Enumerations
-- ---------------------------------------------------------------------------

CREATE TYPE seniority_level AS ENUM (
    'C_SUITE',
    'VP',
    'DIRECTOR',
    'MANAGER',
    'IC'
);

CREATE TYPE alias_type AS ENUM (
    'ACQUISITION',
    'REBRAND',
    'SUBSIDIARY',
    'MANUAL'
);

CREATE TYPE resolution_confidence AS ENUM (
    'HIGH',
    'MEDIUM',
    'LOW',
    'UNRESOLVABLE'
);

CREATE TYPE quarantine_status AS ENUM (
    'PENDING',
    'REVIEWED',
    'RESOLVED',
    'DISCARDED'
);

-- ---------------------------------------------------------------------------
-- accounts
-- Keyed by normalized email domain (ADR 0001).
-- SCD Type 2 snapshot applied by dbt in Sprint 4.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS accounts (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    domain                  VARCHAR(255) NOT NULL,
    name                    VARCHAR(500),
    industry                VARCHAR(100),
    employee_count          INTEGER,
    -- ARR band: STARTUP / SMB / MID_MARKET / ENTERPRISE / LARGE_ENTERPRISE
    arr_band                VARCHAR(30),
    country                 VARCHAR(100),
    -- Enrichment metadata
    firmographic_source     VARCHAR(50),   -- 'clearbit' | 'kickfire' | 'manual'
    firmographic_enriched_at TIMESTAMP WITH TIME ZONE,
    raw_firmographic        JSONB DEFAULT '{}'::jsonb,
    created_at              TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    CONSTRAINT accounts_domain_unique UNIQUE (domain)
);

CREATE INDEX idx_accounts_domain     ON accounts (domain);
CREATE INDEX idx_accounts_industry   ON accounts (industry);
CREATE INDEX idx_accounts_arr_band   ON accounts (arr_band);
CREATE INDEX idx_accounts_updated_at ON accounts (updated_at DESC);

-- ---------------------------------------------------------------------------
-- domain_aliases
-- Maps acquired/rebranded domains to their canonical account domain.
-- e.g. acquired-startup.io → corp.com
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS domain_aliases (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    alias_domain     VARCHAR(255) NOT NULL,
    canonical_domain VARCHAR(255) NOT NULL REFERENCES accounts (domain) ON UPDATE CASCADE,
    alias_type       alias_type NOT NULL DEFAULT 'MANUAL',
    note             TEXT,
    effective_from   TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    effective_to     TIMESTAMP WITH TIME ZONE,   -- NULL = currently active
    created_at       TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    CONSTRAINT domain_aliases_unique UNIQUE (alias_domain, effective_from)
);

CREATE INDEX idx_domain_aliases_alias     ON domain_aliases (alias_domain);
CREATE INDEX idx_domain_aliases_canonical ON domain_aliases (canonical_domain);
-- Partial index: only active aliases
CREATE INDEX idx_domain_aliases_active    ON domain_aliases (alias_domain)
    WHERE effective_to IS NULL;

-- ---------------------------------------------------------------------------
-- committee_members
-- Individual buying-committee stakeholders linked to an Account.
-- SCD Type 2 snapshot applied by dbt in Sprint 4.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS committee_members (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id       UUID NOT NULL REFERENCES accounts (id) ON DELETE CASCADE,
    email            VARCHAR(500) NOT NULL,
    first_name       VARCHAR(200),
    last_name        VARCHAR(200),
    title            VARCHAR(300),
    department       VARCHAR(100),
    seniority_level  seniority_level NOT NULL DEFAULT 'IC',
    -- 0.0–1.0: higher = stronger buying influence (feeds Sprint 5 IntentNetworkModel)
    role_weight      NUMERIC(3, 2) NOT NULL DEFAULT 0.20
                         CHECK (role_weight BETWEEN 0.00 AND 1.00),
    crm_contact_id   VARCHAR(200),  -- Source CRM system's contact ID
    crm_source       VARCHAR(50),   -- 'HUBSPOT' | 'SALESFORCE' | etc.
    is_active        BOOLEAN NOT NULL DEFAULT TRUE,
    last_signal_at   TIMESTAMP WITH TIME ZONE,
    created_at       TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    CONSTRAINT committee_members_email_account_unique UNIQUE (email, account_id)
);

CREATE INDEX idx_committee_members_account_id   ON committee_members (account_id);
CREATE INDEX idx_committee_members_email        ON committee_members (email);
CREATE INDEX idx_committee_members_crm_contact  ON committee_members (crm_contact_id)
    WHERE crm_contact_id IS NOT NULL;
CREATE INDEX idx_committee_members_active       ON committee_members (account_id)
    WHERE is_active = TRUE;

-- ---------------------------------------------------------------------------
-- crm_account_xref
-- Cross-reference table: maps CRM company IDs to canonical account domains.
-- Supports tertiary resolution strategy (CRM company-ID lookup).
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS crm_account_xref (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_domain VARCHAR(255) NOT NULL REFERENCES accounts (domain) ON UPDATE CASCADE,
    crm_source       VARCHAR(50) NOT NULL,   -- 'HUBSPOT' | 'SALESFORCE' | 'PIPEDRIVE'
    crm_company_id   VARCHAR(200) NOT NULL,
    crm_company_name VARCHAR(500),
    created_at       TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    CONSTRAINT crm_account_xref_unique UNIQUE (crm_source, crm_company_id)
);

CREATE INDEX idx_crm_xref_domain ON crm_account_xref (canonical_domain);
CREATE INDEX idx_crm_xref_lookup ON crm_account_xref (crm_source, crm_company_id);

-- ---------------------------------------------------------------------------
-- resolution_quarantine
-- Stores LOW-confidence and UNRESOLVABLE signals for manual review.
-- Never silently drop unresolvable signals — quarantine them instead.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS resolution_quarantine (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id            VARCHAR(200) NOT NULL,
    source_topic        VARCHAR(200) NOT NULL,
    raw_event           JSONB NOT NULL,
    resolution_attempt  JSONB NOT NULL DEFAULT '{}'::jsonb,
    confidence          resolution_confidence NOT NULL DEFAULT 'LOW',
    status              quarantine_status NOT NULL DEFAULT 'PENDING',
    reviewed_by         VARCHAR(200),
    resolved_domain     VARCHAR(255),  -- set when RESOLVED
    reviewed_at         TIMESTAMP WITH TIME ZONE,
    created_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_quarantine_status     ON resolution_quarantine (status);
CREATE INDEX idx_quarantine_event_id   ON resolution_quarantine (event_id);
CREATE INDEX idx_quarantine_created_at ON resolution_quarantine (created_at DESC);
-- Most queries are for PENDING entries
CREATE INDEX idx_quarantine_pending    ON resolution_quarantine (created_at DESC)
    WHERE status = 'PENDING';

-- ---------------------------------------------------------------------------
-- Trigger: updated_at auto-maintenance
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

CREATE TRIGGER accounts_updated_at
    BEFORE UPDATE ON accounts
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER committee_members_updated_at
    BEFORE UPDATE ON committee_members
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER crm_xref_updated_at
    BEFORE UPDATE ON crm_account_xref
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

COMMIT;
