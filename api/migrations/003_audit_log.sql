-- Migration 003: Audit log table for all write operations
-- Every API write (POST/PUT/DELETE) must produce a row here.
-- Append-only: no UPDATE or DELETE ever. Historical truth is inviolable.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'http_method') THEN
        CREATE TYPE http_method AS ENUM ('POST', 'PUT', 'PATCH', 'DELETE');
    END IF;
END;
$$;

CREATE TABLE IF NOT EXISTS audit_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
    request_id      TEXT,                    -- X-Request-ID header
    actor_jwt_sub   TEXT NOT NULL,           -- JWT sub claim (tenant_id)
    http_method     http_method NOT NULL,
    path            TEXT NOT NULL,
    resource_type   TEXT,                    -- e.g. 'account', 'webhook', 'signal'
    resource_id     TEXT,                    -- domain or UUID of the affected resource
    request_body    JSONB,                   -- sanitised (secrets stripped)
    response_status INTEGER NOT NULL,
    client_ip       INET,
    user_agent      TEXT,
    duration_ms     DOUBLE PRECISION,
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- No UPDATE/DELETE triggers — enforced at app layer.
-- Indexes defined in migration 002.

CREATE OR REPLACE VIEW v_audit_log_recent AS
SELECT
    a.id,
    a.tenant_id,
    t.slug         AS tenant_slug,
    a.request_id,
    a.http_method,
    a.path,
    a.resource_type,
    a.resource_id,
    a.response_status,
    a.client_ip,
    a.duration_ms,
    a.occurred_at
FROM audit_log a
JOIN tenants t ON t.id = a.tenant_id
ORDER BY a.occurred_at DESC;
