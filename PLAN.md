# PLAN.md — Sprint Roadmap
## B2B Account Fatigue & Committee Journey Harmonizer (`harmoni`)

> 10 sprints · 2 weeks each · 20 weeks to beta
> Each sprint ends with a deployable, demonstrable increment.
> Sprint 10 exit criteria = 3 paying design-partner customers in production.

---

## Milestone Map

```
Sprint 1  ──  Infrastructure & Project Foundation
Sprint 2  ──  CEP Ingestion Layer (Kafka + Schema Registry)
Sprint 3  ──  Account Identity Resolution Engine
Sprint 4  ──  Data Warehouse, SCD Type 2 & Data Lineage (dbt)
Sprint 5  ──  Intent Network Modeling (Signal Consolidation ML)
Sprint 6  ──  Account Fatigue Score Engine
Sprint 7  ──  Next Best Action (NBA) Orchestrator — Rules Engine
Sprint 8  ──  Multi-Tenant FastAPI + Webhook Dispatch
Sprint 9  ──  RevOps / CMO Dashboard (Next.js 14)
Sprint 10 ──  Beta Hardening, Alerting & Design-Partner Launch
```

---

## Sprint 1 — Infrastructure & Project Foundation
**Duration**: Weeks 1–2
**Goal**: Every developer can run the full stack locally. CI/CD is green from day one.

### Tasks
- [ ] Initialize monorepo structure as defined in `CLAUDE.md` Section 2
- [ ] Create `CLAUDE.md`, `BRAND.md` (stub), `PLAN.md` in root
- [ ] Dockerize all core services: PostgreSQL, ClickHouse, Redis, Kafka + Zookeeper, Schema Registry, Airflow
- [ ] Write `docker-compose.yml` covering all services with health checks
- [ ] Set up Terraform modules for cloud environments (staging, prod): VPC, managed Kafka, managed PostgreSQL
- [ ] Configure `uv` + `pyproject.toml` for Python services; install `ruff`, `pytest`, `pydantic-settings`
- [ ] Bootstrap Next.js 14 app in `dashboard/` with App Router, TypeScript strict mode, Tailwind
- [ ] Set up CI pipeline (GitHub Actions): lint → type-check → unit tests → build on every PR
- [ ] Write `.env.example` with all variables documented (see `CLAUDE.md` Section 8)
- [ ] Create the four initial ADRs in `docs/adr/`
- [ ] Write smoke tests: connect to every service and assert liveness
- [ ] Confirm `BRAND.md` stub is in place before any dashboard work begins

### Definition of Done
- `docker-compose up` starts all services with no manual steps
- CI pipeline passes on `main`
- All team members have confirmed local environment works
- `BRAND.md` stub exists and is referenced in `CLAUDE.md`

---

## Sprint 2 — CEP Ingestion Layer (Kafka + Schema Registry)
**Duration**: Weeks 3–4
**Goal**: Real-time events from any source land in Kafka, schema-validated, keyed by normalized account domain.

### Tasks
- [ ] Define canonical `IntentSignal` Avro schema and register it in Schema Registry
- [ ] Implement `normalize_domain()` utility and unit tests (edge cases: subdomains, aliases, free email providers)
- [ ] Build Kafka producer base class with schema validation and dead-letter queue (DLQ) routing
- [ ] Implement source connectors (stubbed with realistic mock data generators):
  - [ ] Web analytics connector (server log / pixel events)
  - [ ] Email engagement connector (opens, clicks, unsubscribes)
  - [ ] CRM activity connector (HubSpot webhook ingestion)
  - [ ] Webinar attendance connector (Zoom / GoToWebinar webhook)
- [ ] Create Kafka topics: `harmoni.web.pageview`, `harmoni.email.engagement`, `harmoni.crm.contact_activity`, `harmoni.webinar.attendance`
- [ ] Implement Kafka consumer base class with at-least-once delivery guarantees
- [ ] Write integration tests: produce → consume round-trip for each connector
- [ ] Validate DLQ routing: malformed/unregistered-schema messages route to `harmoni.dlq`
- [ ] Document all topic configs (partitions, retention, replication) in `ingestion/kafka/README.md`

### Definition of Done
- All four connectors ingest mock events end-to-end through Kafka
- Schema Registry rejects any message that fails Avro validation
- DLQ contains only malformed messages with a clear error envelope
- 80%+ test coverage on `ingestion/`

---

## Sprint 3 — Account Identity Resolution Engine
**Duration**: Weeks 5–6
**Goal**: Any event from any source is reliably attributed to the correct `Account` entity, regardless of signal fragmentation.

### Tasks
- [ ] Design `Account` and `CommitteeMember` PostgreSQL schemas (draft; finalized in Sprint 4 with SCD)
- [ ] Implement `AccountResolver` class:
  - [ ] Primary resolution: normalized email domain lookup
  - [ ] Secondary resolution: IP-to-company mapping (via Clearbit / Kickfire stub)
  - [ ] Tertiary resolution: CRM company-ID cross-reference
  - [ ] Aliasing table: handle `corp.com` → `acquired-startup.io` mappings
- [ ] Implement `CommitteeMemberResolver`: link individual contact signals to parent `Account`
- [ ] Build enrichment layer: pull firmographic data (industry, size, ARR band) for each resolved `Account`
- [ ] Write resolution confidence scoring: `HIGH` / `MEDIUM` / `LOW` — unresolved signals are quarantined, not dropped
- [ ] Integrate resolver into Kafka consumer pipeline: every consumed event is enriched with `account_id` before downstream processing
- [ ] Build quarantine queue for `LOW`-confidence resolutions requiring manual review
- [ ] Write comprehensive unit tests covering resolution edge cases (personal emails, free domains, missing data)
- [ ] Create ADR: `0005-account-resolution-confidence-tiers.md`

### Definition of Done
- 95%+ of synthetic test events resolve to the correct `Account`
- `LOW`-confidence events route to quarantine, not silently dropped
- Resolution pipeline adds < 50ms latency to event processing (p99)

---

## Sprint 4 — Data Warehouse, SCD Type 2 & Data Lineage
**Duration**: Weeks 7–8
**Goal**: A clean, historically accurate data warehouse where account and contact history is immutable and fully traceable.

### Tasks
- [ ] Initialize dbt project in `pipelines/dbt/`; configure PostgreSQL + ClickHouse targets
- [ ] Build staging models (`stg_`) for all four ingestion sources
- [ ] Build SCD Type 2 dbt snapshots for:
  - [ ] `dim_account`: tracks domain aliases, firmographic changes, account status
  - [ ] `dim_committee_member`: tracks role changes, title changes, company transfers
- [ ] Build intermediate models (`int_`):
  - [ ] `int_account_signals`: unified signal stream per account with `valid_from` / `valid_to` context
  - [ ] `int_committee_composition`: current + historical committee membership per account
- [ ] Build fact models (`fct_`):
  - [ ] `fct_account_signal_hourly`: hourly aggregated signal counts per account, per channel
  - [ ] `fct_committee_engagement`: per-member engagement rates rolled up to account level
- [ ] Add `meta` tags (owner, source, refresh cadence) to all dbt models
- [ ] Build Airflow DAG: `dag_hourly_account_metrics` — runs dbt hourly, updates ClickHouse aggregates
- [ ] Set up dbt tests: `not_null`, `unique`, `accepted_values` on all primary keys and critical fields
- [ ] Validate SCD Type 2 immutability: write tests proving no existing rows are mutated
- [ ] Generate dbt docs and confirm lineage graph is complete

### Definition of Done
- Full lineage graph visible in dbt docs with no undocumented nodes
- SCD Type 2 snapshots pass immutability tests
- Hourly Airflow DAG runs successfully on synthetic data with no failures for 24 hours

---

## Sprint 5 — Intent Network Modeling
**Duration**: Weeks 9–10
**Goal**: Weak signals from multiple committee members are consolidated into a single, reliable account-level Intent Score.

### Tasks
- [ ] Define `IntentScore` schema: score (0–100), confidence, signal_breakdown, computed_at
- [ ] Design feature set for Intent Network Model:
  - [ ] Signal recency decay (exponential decay by signal age)
  - [ ] Role-weighted aggregation (VP/C-suite signals weighted higher)
  - [ ] Channel diversity bonus (signals from 3+ channels increase confidence)
  - [ ] Velocity features: signal acceleration / deceleration over 7/14/30-day windows
- [ ] Implement feature engineering pipeline in `scoring/intent/features.py`
- [ ] Train baseline logistic regression model on synthetic labeled dataset (deal won/lost ground truth)
- [ ] Implement `IntentNetworkModel` class with `predict(account_id) -> IntentScore`
- [ ] Build Churn Predictor (`ChurnPredictor`): binary classifier for 30-day deal abandonment risk
- [ ] Build offline evaluation harness: precision, recall, AUC-ROC per model
- [ ] Write Airflow DAG: `dag_intent_score_refresh` — recomputes scores every 4 hours
- [ ] Store scores in PostgreSQL `account_scores` table with full timestamp history
- [ ] Write model card for each trained model in `scoring/intent/MODEL_CARD.md`

### Definition of Done
- `IntentScore` and `ChurnProbability` are computed for 100% of active accounts
- Baseline AUC-ROC ≥ 0.70 on held-out synthetic test set
- Score refresh DAG runs without failure for 48 hours
- Model cards written and committed

---

## Sprint 6 — Account Fatigue Score Engine
**Duration**: Weeks 11–12
**Goal**: Every target account has a real-time composite Fatigue Score that prevents over-contact and triggers intelligent cooldowns.

### Tasks
- [ ] Define `AccountFatigueScore` schema: score (0–100), severity (LOW/MEDIUM/HIGH/CRITICAL), components, computed_at
- [ ] Implement fatigue component calculators:
  - [ ] Outreach frequency score: messages sent in last 7/14/30 days vs. account-type baseline
  - [ ] Engagement decay score: rolling open/click/reply rate trend (falling = rising fatigue)
  - [ ] Unsubscribe / negative signal score: hard negative signals (unsubscribes, spam reports)
  - [ ] Contact concentration score: penalty for contacting the same member repeatedly
  - [ ] Recency score: time since last meaningful engagement (reply, meeting booked)
- [ ] Implement composite scoring with configurable weights per `Account` segment
- [ ] Implement `ActionCooldown` engine backed by Redis:
  - [ ] Per-account cooldown (all outreach paused)
  - [ ] Per-member cooldown (specific contact paused)
  - [ ] Dynamic TTL: severity-driven cooldown duration (LOW=24h, MEDIUM=72h, HIGH=7d, CRITICAL=30d)
- [ ] Build Airflow DAG: `dag_fatigue_score_refresh` — runs every 30 minutes
- [ ] Write unit tests covering all component calculators with boundary conditions
- [ ] Write integration test: confirm Redis cooldown lock is set when score crosses threshold

### Definition of Done
- All active accounts have a live `AccountFatigueScore` refreshed every 30 minutes
- Redis cooldown locks are set/cleared correctly based on score thresholds
- Zero false negatives on CRITICAL fatigue in integration test suite

---

## Sprint 7 — Next Best Action (NBA) Orchestrator — Rules Engine
**Duration**: Weeks 13–14
**Goal**: The system recommends the correct next action for every account automatically, based on a coherent view of fatigue, intent, and churn risk.

### Tasks
- [ ] Define `NextBestAction` schema: action_type, priority, rationale, expiry, triggered_by, account_id
- [ ] Implement action type taxonomy:
  - [ ] `COOLDOWN`: Pause all outreach
  - [ ] `NURTURE`: Low-pressure educational content sequence
  - [ ] `RE_ENGAGE`: Personalized re-engagement for declining accounts
  - [ ] `ACCELERATE`: High-intent accounts — escalate cadence
  - [ ] `EXEC_ESCALATION`: Route to AE/VP for executive-to-executive outreach
  - [ ] `PRICING_TRIGGER`: Surface pricing/ROI content (high intent + financial stakeholder active)
  - [ ] `DEAL_REVIEW`: Internal flag — churn probability > threshold, requires human review
- [ ] Build `NBAOrchestrator` rules engine: decision tree mapping (FatigueScore × IntentScore × ChurnProbability) → `NextBestAction`
- [ ] Implement action dispatch interface: `ActionDispatcher` abstract class with concrete implementations for HubSpot, Salesloft, Slack (stub)
- [ ] Add `FEATURE_RL_ORCHESTRATOR` feature flag guard: production always uses rules engine
- [ ] Write `orchestrator/rl/` stub module (isolated, non-importable from prod paths)
- [ ] Build Airflow DAG: `dag_nba_orchestration` — runs every hour, emits actions for all active accounts
- [ ] Write comprehensive decision-tree unit tests: every action_type has coverage for edge cases
- [ ] Add conflict resolution: only one active NBA per account at a time (latest overwrites unless CRITICAL)

### Definition of Done
- Every active account receives a `NextBestAction` every hour
- Action dispatch stubs log correctly to test harness
- Feature flag prevents RL module from executing in any test or prod environment
- 100% action type coverage in unit tests

---

## Sprint 8 — Multi-Tenant FastAPI + Webhook Dispatch
**Duration**: Weeks 15–16
**Goal**: External customers can connect harmoni to their stack via a secure, well-documented API.

### Tasks
- [ ] Implement multi-tenant architecture in FastAPI:
  - [ ] JWT authentication with tenant isolation middleware
  - [ ] Schema-based tenant isolation in PostgreSQL
  - [ ] Rate limiting per tenant (Redis-backed)
- [ ] Build API routers:
  - [ ] `GET /accounts/{domain}` — full account profile: scores, members, active NBA
  - [ ] `GET /accounts/{domain}/fatigue` — current fatigue score + components
  - [ ] `GET /accounts/{domain}/intent` — intent score + signal breakdown
  - [ ] `GET /accounts/{domain}/nba` — current next best action
  - [ ] `POST /accounts/{domain}/signals` — ingest ad-hoc signals from external sources
  - [ ] `GET /accounts` — paginated account list with filtering by score ranges
  - [ ] `POST /tenants` — admin: provision new tenant
  - [ ] `GET /health` — liveness check
- [ ] Implement outbound webhook dispatch: tenants register webhook URLs to receive NBA events in real time
- [ ] Write Pydantic v2 request/response schemas for all endpoints
- [ ] Set up OpenAPI docs at `/docs` — all endpoints fully documented with examples
- [ ] Write API integration tests with `httpx` + `pytest-asyncio`
- [ ] Add structured logging (JSON) + request tracing headers (`X-Request-ID`)
- [ ] Set up API versioning (`/v1/`) from the start

### Definition of Done
- All routes return correct responses for happy path and error cases
- Multi-tenant isolation verified: tenant A cannot read tenant B's data
- Webhook dispatch delivers NBA events to test endpoint within 5 seconds
- OpenAPI docs are complete and accurate

---

## Sprint 9 — RevOps / CMO Dashboard (Next.js 14)
**Duration**: Weeks 17–18
**Goal**: Marketing and RevOps teams have a clear, actionable view of their entire ABM portfolio's health.

> **All visual design decisions come from `BRAND.md` before any component is written.**

### Tasks
- [ ] Read and implement `BRAND.md` design tokens (colors, typography, spacing) into Tailwind config
- [ ] Build authentication flow: login, JWT storage, protected routes
- [ ] Build core dashboard pages:
  - [ ] `/dashboard` — Portfolio Overview: top fatigued accounts, top intent accounts, NBA queue
  - [ ] `/accounts` — Account list with sort/filter by fatigue, intent, churn risk
  - [ ] `/accounts/[domain]` — Account Detail: committee members, signal timeline, score history, active NBA
  - [ ] `/settings` — Tenant config, webhook registration, connector status
- [ ] Build reusable components (per `BRAND.md` specs):
  - [ ] `FatigueScoreBadge` — severity-colored badge with score
  - [ ] `IntentScoreGauge` — visual gauge for intent 0–100
  - [ ] `CommitteeHeatmap` — grid of members × channels showing engagement density
  - [ ] `NBAActionCard` — current recommendation with rationale and one-click dispatch
  - [ ] `SignalTimeline` — chronological event feed for an account
- [ ] Implement React Query data fetching layer in `dashboard/lib/api/`
- [ ] Add empty states and loading skeletons for all data-dependent views (per `BRAND.md`)
- [ ] Write component tests with `@testing-library/react`

### Definition of Done
- All five pages render correctly with live API data
- `BRAND.md` is consulted and cited for every visual decision in this sprint
- No component ships without a corresponding `BRAND.md` entry
- Lighthouse accessibility score ≥ 90

---

## Sprint 10 — Beta Hardening, Alerting & Design-Partner Launch
**Duration**: Weeks 19–20
**Goal**: Three paying design-partner customers are live in production. The system is observable, resilient, and supportable.

### Tasks

**Reliability & Performance**
- [ ] Load test all API endpoints: 500 concurrent requests, p99 < 200ms
- [ ] Load test Kafka ingestion: 10,000 events/minute sustained, zero message loss
- [ ] Add database indexes for all query-critical columns (account domain, score timestamps)
- [ ] Implement circuit breakers on all external API calls (HubSpot, Salesloft, enrichment)
- [ ] Set up PostgreSQL connection pooling (PgBouncer)

**Observability**
- [ ] Integrate structured logging → Datadog / Grafana Loki
- [ ] Build Grafana dashboards:
  - [ ] Kafka lag per topic
  - [ ] Airflow DAG success rate and duration
  - [ ] API latency (p50/p95/p99) per endpoint
  - [ ] Account score computation freshness
- [ ] Set up PagerDuty / OpsGenie alerts:
  - [ ] Kafka consumer lag > 5 minutes
  - [ ] Airflow DAG failure
  - [ ] API error rate > 1% over 5 minutes
  - [ ] NBA dispatch failure for any CRITICAL fatigue account

**Security**
- [ ] Run OWASP ZAP scan on API; resolve all HIGH/CRITICAL findings
- [ ] Confirm tenant isolation with penetration test (cross-tenant data access attempt)
- [ ] Rotate all secrets from `.env.example`; confirm no secrets in git history
- [ ] Enable audit log: every API write operation logged with tenant, user, timestamp

**Beta Launch**
- [ ] Onboard Design Partner 1: configure tenant, connect CRM webhook, validate first account scores
- [ ] Onboard Design Partner 2
- [ ] Onboard Design Partner 3
- [ ] Collect structured feedback: NPS survey + weekly 30-min call per partner
- [ ] Triage and prioritize post-beta backlog

### Definition of Done
- Three design-partner tenants live in production for ≥ 7 days with no Sev-1 incidents
- All alerting rules are active and have been tested (alert fired + resolved at least once)
- Security scan shows zero unresolved HIGH/CRITICAL findings
- Post-beta backlog created and prioritized for Sprint 11+

---

## Risk Register

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| **Positioning creep** — product described as "surveillance" or "lead tracking" in any surface | Medium | Critical | CLAUDE.md Hard Rule #1; review all copy before customer-facing release |
| **Identity resolution accuracy** < 90% | High | High | Sprint 3 quarantine queue; enrichment fallbacks; confidence tiers |
| **Kafka schema drift** — producers send unregistered schemas | Medium | High | Schema Registry enforced; CI test validates all schemas on PR |
| **SCD Type 2 mutation** — developer accidentally updates historical rows | Low | Critical | dbt immutability tests run on every DAG execution |
| **RL orchestrator leaks to production** | Low | High | Feature flag in CI; RL module not importable from prod paths |
| **Tenant data isolation failure** | Low | Critical | Penetration test in Sprint 10; middleware unit tests in Sprint 8 |
| **OpenAI API cost overrun** | Medium | Medium | Embeddings only used for auxiliary enrichment; batching enabled; budget alerts set |
| **Design-partner churn before Sprint 10** | Medium | High | Weekly calls from Sprint 9 onward; product feedback loop built into Sprint 10 |

---

## Backlog (Post-Beta, Sprint 11+)

- RL-based NBA orchestrator (behind feature flag, requires Sprint 5–7 data to train)
- LinkedIn signal ingestion connector
- G2 / intent data provider integration (Bombora, G2)
- Slack / Teams NBA notification integration (native, not just webhook)
- Account health scoring API for HubSpot/Salesforce native embedding
- Self-serve tenant onboarding flow
- Multi-language dashboard (ES/EN at minimum)
- SOC 2 Type II audit preparation
