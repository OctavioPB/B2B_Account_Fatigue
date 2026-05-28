-- =============================================================================
-- Sprint 4: Raw Event Landing Tables
-- =============================================================================
-- Kafka consumers write deserialized events into these tables.
-- dbt staging models (stg_*) read from these as their source of truth.
-- These are append-only; rows are never updated or deleted.
-- SCD Type 2 history is managed by dbt snapshots, not here.
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- Shared enum: signal strength (mirrors Avro schema)
-- ---------------------------------------------------------------------------

DO $$ BEGIN
    CREATE TYPE signal_strength AS ENUM ('WEAK', 'MEDIUM', 'STRONG');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE source_system AS ENUM ('WEB', 'EMAIL', 'CRM', 'WEBINAR', 'MANUAL');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ---------------------------------------------------------------------------
-- raw_web_pageviews
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS raw_web_pageviews (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id                VARCHAR(200) NOT NULL,
    account_domain          VARCHAR(255),
    contact_email           VARCHAR(500),
    source_system           source_system NOT NULL DEFAULT 'WEB',
    event_type              VARCHAR(100) NOT NULL,
    occurred_at             TIMESTAMP WITH TIME ZONE NOT NULL,
    ingested_at             TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    signal_strength         signal_strength NOT NULL DEFAULT 'WEAK',
    page_url                TEXT,
    page_title              VARCHAR(500),
    page_category           VARCHAR(50),           -- PRICING / PRODUCT / BLOG / etc.
    time_on_page_seconds    INTEGER,
    session_id              VARCHAR(200),
    user_agent              TEXT,
    properties              JSONB DEFAULT '{}'::jsonb,
    _loaded_at              TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_raw_web_domain      ON raw_web_pageviews (account_domain);
CREATE INDEX IF NOT EXISTS idx_raw_web_occurred_at ON raw_web_pageviews (occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_raw_web_event_id    ON raw_web_pageviews (event_id);

-- ---------------------------------------------------------------------------
-- raw_email_engagements
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS raw_email_engagements (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id                VARCHAR(200) NOT NULL,
    account_domain          VARCHAR(255),
    contact_email           VARCHAR(500),
    source_system           source_system NOT NULL DEFAULT 'EMAIL',
    event_type              VARCHAR(100) NOT NULL,
    occurred_at             TIMESTAMP WITH TIME ZONE NOT NULL,
    ingested_at             TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    signal_strength         signal_strength NOT NULL DEFAULT 'WEAK',
    campaign_id             VARCHAR(200),
    message_id              VARCHAR(200),
    engagement_type         VARCHAR(50) NOT NULL,  -- OPENED / CLICKED / UNSUBSCRIBED / etc.
    is_negative             BOOLEAN NOT NULL DEFAULT FALSE,
    properties              JSONB DEFAULT '{}'::jsonb,
    _loaded_at              TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_raw_email_domain      ON raw_email_engagements (account_domain);
CREATE INDEX IF NOT EXISTS idx_raw_email_occurred_at ON raw_email_engagements (occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_raw_email_event_id    ON raw_email_engagements (event_id);
CREATE INDEX IF NOT EXISTS idx_raw_email_negative    ON raw_email_engagements (account_domain)
    WHERE is_negative = TRUE;

-- ---------------------------------------------------------------------------
-- raw_crm_contact_activities
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS raw_crm_contact_activities (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id                VARCHAR(200) NOT NULL,
    account_domain          VARCHAR(255),
    contact_email           VARCHAR(500),
    source_system           source_system NOT NULL DEFAULT 'CRM',
    event_type              VARCHAR(100) NOT NULL,
    occurred_at             TIMESTAMP WITH TIME ZONE NOT NULL,
    ingested_at             TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    signal_strength         signal_strength NOT NULL DEFAULT 'WEAK',
    crm_source              VARCHAR(50),            -- HUBSPOT / SALESFORCE / PIPEDRIVE
    crm_contact_id          VARCHAR(200),
    crm_company_id          VARCHAR(200),
    activity_type           VARCHAR(100),           -- EMAIL_SENT / MEETING_BOOKED / DEAL_STAGE_CHANGED / etc.
    raw_payload             JSONB DEFAULT '{}'::jsonb,
    properties              JSONB DEFAULT '{}'::jsonb,
    _loaded_at              TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_raw_crm_domain      ON raw_crm_contact_activities (account_domain);
CREATE INDEX IF NOT EXISTS idx_raw_crm_occurred_at ON raw_crm_contact_activities (occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_raw_crm_event_id    ON raw_crm_contact_activities (event_id);
CREATE INDEX IF NOT EXISTS idx_raw_crm_source      ON raw_crm_contact_activities (crm_source, crm_company_id);

-- ---------------------------------------------------------------------------
-- raw_webinar_attendances
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS raw_webinar_attendances (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id                    VARCHAR(200) NOT NULL,
    account_domain              VARCHAR(255),
    contact_email               VARCHAR(500),
    source_system               source_system NOT NULL DEFAULT 'WEBINAR',
    event_type                  VARCHAR(100) NOT NULL,
    occurred_at                 TIMESTAMP WITH TIME ZONE NOT NULL,
    ingested_at                 TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    signal_strength             signal_strength NOT NULL DEFAULT 'WEAK',
    webinar_id                  VARCHAR(200),
    webinar_title               VARCHAR(500),
    webinar_provider            VARCHAR(50),   -- ZOOM / GOTOWEBINAR / BIGMARKER / HOPIN
    attendance_type             VARCHAR(50),   -- REGISTERED / ATTENDED_LIVE / WATCHED_RECORDING / NO_SHOW
    attended_duration_seconds   INTEGER,
    questions_asked             INTEGER DEFAULT 0,
    polls_answered              INTEGER DEFAULT 0,
    webinar_topic               VARCHAR(100),  -- PRODUCT_DEMO / THOUGHT_LEADERSHIP / etc.
    properties                  JSONB DEFAULT '{}'::jsonb,
    _loaded_at                  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_raw_webinar_domain      ON raw_webinar_attendances (account_domain);
CREATE INDEX IF NOT EXISTS idx_raw_webinar_occurred_at ON raw_webinar_attendances (occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_raw_webinar_event_id    ON raw_webinar_attendances (event_id);

-- ---------------------------------------------------------------------------
-- ClickHouse mirror: fct_account_signal_hourly
-- (created in ClickHouse separately; documented here for reference)
-- ---------------------------------------------------------------------------
-- CREATE TABLE harmoni.fct_account_signal_hourly
-- (
--     account_domain  LowCardinality(String),
--     signal_hour     DateTime,
--     source_system   LowCardinality(String),
--     signal_count    UInt32,
--     strong_count    UInt32,
--     negative_count  UInt32,
--     unique_members  UInt32,
--     _refreshed_at   DateTime DEFAULT now()
-- )
-- ENGINE = ReplacingMergeTree(_refreshed_at)
-- PARTITION BY toYYYYMM(signal_hour)
-- ORDER BY (account_domain, signal_hour, source_system);

COMMIT;
