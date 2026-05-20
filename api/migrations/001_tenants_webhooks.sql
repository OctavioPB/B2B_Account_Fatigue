-- Migration 001: Multi-tenant foundation + webhook registrations
-- Idempotent: uses IF NOT EXISTS throughout.
-- Never DROP or ALTER in a way that destroys data; extend only.

-- ---------------------------------------------------------------------------
-- Tenants
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS tenants (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug            TEXT NOT NULL UNIQUE,          -- URL-safe identifier, e.g. "acme-corp"
    display_name    TEXT NOT NULL,
    schema_name     TEXT NOT NULL UNIQUE,          -- PostgreSQL schema for data isolation
    plan            TEXT NOT NULL DEFAULT 'starter' CHECK (plan IN ('starter', 'growth', 'enterprise')),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    rate_limit_rpm  INTEGER NOT NULL DEFAULT 60,   -- requests per minute; overrideable per tenant
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tenants_slug        ON tenants (slug);
CREATE INDEX IF NOT EXISTS idx_tenants_schema_name ON tenants (schema_name);
CREATE INDEX IF NOT EXISTS idx_tenants_is_active   ON tenants (is_active) WHERE is_active = TRUE;

-- Trigger: keep updated_at current
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'trg_tenants_updated_at'
    ) THEN
        CREATE TRIGGER trg_tenants_updated_at
        BEFORE UPDATE ON tenants
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    END IF;
END;
$$;

-- ---------------------------------------------------------------------------
-- Webhook registrations
-- ---------------------------------------------------------------------------

-- Webhook event types that harmoni can emit
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'webhook_event_type') THEN
        CREATE TYPE webhook_event_type AS ENUM (
            'nba.created',
            'nba.superseded',
            'fatigue.critical',
            'fatigue.high',
            'cooldown.set',
            'cooldown.cleared',
            'churn.high',
            'churn.critical',
            'signal.ingested'
        );
    END IF;
END;
$$;

CREATE TABLE IF NOT EXISTS webhook_registrations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
    target_url      TEXT NOT NULL,
    description     TEXT,
    secret          TEXT NOT NULL,                 -- HMAC-SHA256 signing secret (stored hashed)
    event_types     webhook_event_type[] NOT NULL, -- subscribed events
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    failure_count   INTEGER NOT NULL DEFAULT 0,    -- consecutive delivery failures
    last_triggered_at  TIMESTAMPTZ,
    last_success_at    TIMESTAMPTZ,
    last_failure_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_webhooks_tenant_id  ON webhook_registrations (tenant_id);
CREATE INDEX IF NOT EXISTS idx_webhooks_is_active  ON webhook_registrations (tenant_id, is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_webhooks_event_types ON webhook_registrations USING GIN (event_types);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'trg_webhooks_updated_at'
    ) THEN
        CREATE TRIGGER trg_webhooks_updated_at
        BEFORE UPDATE ON webhook_registrations
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    END IF;
END;
$$;

-- ---------------------------------------------------------------------------
-- Webhook delivery log (audit trail; append-only)
-- ---------------------------------------------------------------------------

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'webhook_delivery_status') THEN
        CREATE TYPE webhook_delivery_status AS ENUM ('pending', 'success', 'failed', 'retrying');
    END IF;
END;
$$;

CREATE TABLE IF NOT EXISTS webhook_delivery_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    webhook_id      UUID NOT NULL REFERENCES webhook_registrations (id) ON DELETE CASCADE,
    tenant_id       UUID NOT NULL,
    event_type      webhook_event_type NOT NULL,
    payload         JSONB NOT NULL,
    status          webhook_delivery_status NOT NULL DEFAULT 'pending',
    http_status     INTEGER,                       -- response status code from target
    attempt_count   INTEGER NOT NULL DEFAULT 0,
    last_attempt_at TIMESTAMPTZ,
    delivered_at    TIMESTAMPTZ,
    error_detail    TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_delivery_log_webhook_id  ON webhook_delivery_log (webhook_id);
CREATE INDEX IF NOT EXISTS idx_delivery_log_tenant_id   ON webhook_delivery_log (tenant_id);
CREATE INDEX IF NOT EXISTS idx_delivery_log_status      ON webhook_delivery_log (status) WHERE status IN ('pending', 'retrying');
CREATE INDEX IF NOT EXISTS idx_delivery_log_created_at  ON webhook_delivery_log (created_at DESC);

-- ---------------------------------------------------------------------------
-- Rate-limit audit (Redis is authoritative; this is a slow-path audit log)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS rate_limit_violations (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
    endpoint    TEXT NOT NULL,
    client_ip   INET,
    rpm_limit   INTEGER NOT NULL,
    rpm_actual  INTEGER NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rate_limit_tenant_id   ON rate_limit_violations (tenant_id);
CREATE INDEX IF NOT EXISTS idx_rate_limit_occurred_at ON rate_limit_violations (occurred_at DESC);

-- ---------------------------------------------------------------------------
-- View: active webhooks per tenant with event type expansion
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW v_active_webhooks AS
SELECT
    w.id,
    w.tenant_id,
    t.slug          AS tenant_slug,
    w.target_url,
    w.description,
    unnest(w.event_types) AS event_type,
    w.failure_count,
    w.last_success_at,
    w.created_at
FROM webhook_registrations w
JOIN tenants t ON t.id = w.tenant_id
WHERE w.is_active = TRUE
  AND t.is_active = TRUE;
