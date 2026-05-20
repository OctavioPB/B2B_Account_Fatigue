# 0007: OWASP ASVS v4.0 Security Hardening for Beta Launch
**Status**: Accepted  
**Date**: 2026-05-17

---

## Context

harmoni processes sensitive commercial signals — email engagement, CRM activity, intent data — for B2B buying committees. Before opening the platform to design partners, we needed confidence that:

1. Tenant data is provably isolated (one tenant cannot read another's accounts or scores)
2. HTTP responses do not leak server internals or enable common browser attacks (XSS, clickjacking, MIME sniffing)
3. All write operations are attributable to a specific tenant for compliance and incident investigation
4. Noisy or flaky downstream integrations (HubSpot, Salesforce, Clearbit, Slack, OpenAI) cannot cascade into platform-wide failures
5. The API can withstand 500 concurrent users without exhausting database connections

The threat model is primarily: compromised partner JWT, misconfigured webhook, or dependency outage — not nation-state attacks. We scoped hardening to OWASP ASVS Level 2 (standard application), not Level 3 (high-value target).

---

## Decision

We implemented five interconnected controls as part of Sprint 10:

### 1. OWASP Security Response Headers (`api/middleware/security.py`)

Every HTTP response from the FastAPI application now carries:

| Header | Value | Threat mitigated |
|--------|-------|-----------------|
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` | SSL stripping, HTTP downgrade |
| `X-Content-Type-Options` | `nosniff` | MIME-type confusion attacks |
| `X-Frame-Options` | `DENY` | Clickjacking |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | Referrer leakage |
| `Permissions-Policy` | `camera=(), microphone=(), geolocation=()` | Capability creep |
| `Cache-Control` | `no-store, max-age=0` + `Pragma: no-cache` | Sensitive data in caches |
| `Content-Security-Policy` | `default-src 'none'; frame-ancestors 'none'` (API) / relaxed (docs) | XSS, injection |
| _(removed)_ | `Server`, `X-Powered-By` | Fingerprinting |

The CSP is differentiated by path: `/docs` and `/redoc` get a relaxed policy to allow Swagger UI's CDN-hosted scripts. All other paths get the strictest possible CSP for an API surface.

### 2. Append-Only Audit Log (`api/middleware/audit.py`, `api/migrations/003_audit_log.sql`)

All write operations (POST, PUT, PATCH, DELETE) are recorded in a PostgreSQL `audit_log` table. Key design choices:

- **Fire-and-forget**: `asyncio.create_task` ensures audit writes never add latency to the API response path. A failed write emits a structured ERROR log but does not fail the request.
- **Body sanitisation**: `_sanitise_body` redacts any JSON field whose key matches `(secret|password|token|key|credential)` — replaced with `"***REDACTED***"` before storage. Body is capped at 8 KB.
- **No UPDATE or DELETE on audit rows**: enforced at the database level via a `before_update` and `before_delete` trigger that raises an exception. Historical attribution is inviolable.
- **Tenant attribution**: every row carries `tenant_id` (from JWT claims) and `client_ip` for incident investigations.

### 3. Circuit Breakers for External Integrations (`api/circuit_breakers.py`)

Five downstream integrations — HubSpot, Salesloft, Slack, Clearbit, OpenAI — are wrapped in a three-state circuit breaker (CLOSED → OPEN → HALF_OPEN). Each breaker has independently tuned thresholds:

- **HubSpot / Salesloft**: trip at 5 consecutive failures, 30s recovery window
- **Clearbit enrichment**: trip at 3 failures, 120s recovery (external enrichment is non-critical)
- **Slack alerting**: trip at 10 failures, 60s recovery (higher tolerance because alerts are observability, not data-path)
- **OpenAI embeddings**: trip at 3 failures, 120s recovery (embeddings are async, not in request path)

When a breaker is OPEN, calls to that integration raise `CircuitOpenError` immediately rather than waiting for a timeout. This prevents thundering-herd on recovery. The `GET /health` endpoint surfaces breaker state so Grafana alerts can fire before users notice degradation.

### 4. Tenant Isolation Verification (`api/tests/test_security.py`)

Penetration-style tests were added to the automated suite:

- **Cross-tenant UUID divergence**: same domain, different tenant JWTs → provably different account IDs
- **Tampered JWT rejection**: modified payload (alg swap, claim injection) → 401
- **Expired token rejection**: → 401
- **Cross-tenant webhook delete**: tenant B cannot delete tenant A's webhook → 404 (prevents enumeration)
- **Injection prevention**: SQL injection patterns in domain parameter → 422 or 404, never 500; null bytes, path traversal, XSS in email field all handled at the Pydantic validation layer

### 5. PgBouncer Connection Pooling (`infra/docker/pgbouncer.ini`)

PostgreSQL `max_connections = 200` would be exhausted at 500 concurrent API users if each request held a connection for its full lifetime. PgBouncer in **transaction mode** ensures a server connection is held only during active query execution (typically 1–5ms), not during the full HTTP request lifecycle (which includes JWT validation, response serialisation, network round-trips).

With `default_pool_size = 25` per user/db pair, 500 concurrent API users map to ≈ 3 active server connections under normal load (500 users × 5ms average query / 1000ms per second = 2.5 simultaneous queries).

Airflow DAGs use a separate pool in **session mode** with `pool_size = 20` because DAG task connections are long-running and incompatible with transaction-mode multiplexing.

---

## Consequences

**Positive**:

- The automated test suite now exercises OWASP ASVS Level 2 controls on every CI run — regressions are caught before merge.
- The audit log provides a forensic trail for any data access incident affecting design-partner accounts. This is a hard requirement for SOC 2 Type II (post-beta).
- Circuit breakers mean a Clearbit or OpenAI outage cannot degrade the fatigue scoring or NBA dispatch paths — the integrations fail gracefully with logged errors.
- PgBouncer allows the platform to serve 500 concurrent users on a `db.t3.large` (200 max_connections) without connection exhaustion, deferring vertical scaling costs.

**Trade-offs and limitations**:

- The audit log uses fire-and-forget writes. In a catastrophic Redis failure during a concurrent write storm, some audit rows may be lost. This is an acceptable trade-off — the alternative (synchronous writes) would add 5–15ms to every write request.
- HSTS is set at the application layer. In production, it must also be set at the load balancer / CDN layer to cover the initial HTTP→HTTPS redirect before the app receives the request. The current implementation covers all responses _after_ the first TLS handshake.
- Circuit breakers use in-process state (asyncio Lock, instance variables). In a multi-process deployment (multiple uvicorn workers or pods), each process maintains independent breaker state. This means a single degraded integration may not trip the breaker across all pods simultaneously. Accepted for MVP; a Redis-backed distributed breaker is in the post-beta backlog.
- The CSP `default-src 'none'` policy blocks all inline scripts and external resources on API endpoints. If the API ever serves HTML (e.g., an OAuth callback page), the CSP will need to be extended. The `_HTML_PATHS` set in `security.py` is the designated extension point.
- Body sanitisation in the audit log is keyword-based, not schema-aware. A field named `passphrase` would not be redacted. The `_SECRET_PATTERN` regex should be reviewed and extended as the API surface grows.

**Follow-up work** (tracked in `docs/backlog/post_beta.md`):

- Replace in-process circuit breaker state with Redis-backed distributed state
- Extend `_SECRET_PATTERN` to cover `passphrase`, `bearer`, `auth`, `private_key`
- Enable TLS in `pgbouncer.ini` (`server_tls_sslmode = require`) once RDS CA cert is provisioned
- Add OWASP ZAP automated scan to CI pipeline as a scheduled job
- Begin SOC 2 Type II audit preparation (access reviews, change management, vendor controls)
