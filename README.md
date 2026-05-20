# harmoni

**Revenue Intelligence & Deal Protection for B2B buying committees.**

harmoni prevents deals from dying silently. It tracks the collective health of every target account's buying committee — not individual contacts — and tells revenue teams exactly what to do next: pause outreach, escalate to a VP, trigger a pricing conversation, or re-engage a fading deal. The result is fewer lost deals from over-contact, better timing on high-intent accounts, and a shared playbook across marketing and sales.

---

## The Problem

B2B purchase decisions are made by committees — CFO, CTO, COO, and their teams — but most marketing automation tools treat each stakeholder as an isolated lead. The consequences are predictable:

- Sales and marketing send overlapping, contradictory messages to the same account
- High-value contacts disengage because they're touched too often or at the wrong time
- No one has a single view of whether an account is heating up or going cold

harmoni solves this by aggregating signals from every committee member into a single account-level score, then recommending the one action most likely to protect or advance the deal.

---

## How It Works

```
CRM events ──┐
Web signals ──┤  Kafka CEP  ──▶  Account Identity  ──▶  Scoring Engine  ──▶  NBA Orchestrator
Email data ──┤  (schema-      (domain resolution,      (Fatigue Score,       (rules engine →
Webinar ──────┘   validated)    committee linking)      Intent Score,          action dispatch)
                                                        Churn Probability)
                                                              │
                                                        ┌─────▼─────┐
                                                        │  harmoni  │
                                                        │    API    │──▶ Partner webhooks
                                                        └─────▲─────┘
                                                              │
                                                        RevOps Dashboard
```

**Account Fatigue Score** (0–100, refreshed every 30 min): measures collective outreach frequency, engagement decay, unsubscribe signals, and contact concentration across the committee. A HIGH or CRITICAL score triggers an automatic cooldown.

**Intent Score** (0–100, refreshed every 4 hr): aggregates weak signals from multiple committee members, weighted by role and recency, into a single account-level intent reading using the Intent Network Model.

**Next Best Action**: the system selects one recommended action per account — `COOLDOWN`, `NURTURE`, `RE_ENGAGE`, `ACCELERATE`, `EXEC_ESCALATION`, `PRICING_TRIGGER`, or `DEAL_REVIEW` — based on the intersection of all three scores. Actions are dispatched to CRM systems and partner webhooks in real time.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Event streaming | Apache Kafka + Confluent Schema Registry |
| Workflow orchestration | Apache Airflow 2.9 |
| Data transformation | dbt (staging → intermediate → mart, SCD Type 2) |
| Operational database | PostgreSQL 15 |
| Analytics store | ClickHouse |
| Real-time state | Redis 7 (cooldown locks, rate limiting) |
| ML / scoring | Python 3.11 + scikit-learn |
| Backend API | FastAPI + Pydantic v2 (multi-tenant, JWT auth) |
| Connection pooling | PgBouncer (transaction mode) |
| Frontend dashboard | Next.js 14 (App Router, TypeScript strict) |
| Infrastructure | Terraform + Docker Compose |
| Observability | Prometheus alert rules, Grafana dashboards |

---

## Prerequisites

- **Docker Desktop** 4.x+ (for the full local stack)
- **Python 3.11+** with [`uv`](https://github.com/astral-sh/uv)
- **Node.js 20+** and npm (for the dashboard)
- **Git**

---

## Setup

### 1. Clone and configure environment

```bash
git clone https://github.com/your-org/harmoni.git
cd harmoni

cp .env.example .env
# Edit .env — set API_SECRET_KEY and WEBHOOK_SIGNING_SECRET at minimum.
# Use `openssl rand -hex 32` to generate each secret.
```

### 2. Start the infrastructure stack

```bash
docker-compose up -d
```

This starts PostgreSQL, ClickHouse, Redis, Kafka, Zookeeper, Schema Registry, and Airflow (webserver + scheduler). Wait ~60 seconds for all health checks to pass:

```bash
docker-compose ps   # all services should show "healthy"
```

Airflow UI is available at [http://localhost:8080](http://localhost:8080) (user: `airflow`, password: `airflow`).

### 3. Install Python dependencies

```bash
# API + ingestion + scoring (recommended for local development)
uv pip install -e ".[api,ingestion,scoring,dev]"

# Or install everything:
uv pip install -e ".[all,dev]"
```

### 4. Run database migrations

```bash
# Core schema (tenants, webhooks, audit log)
psql $DATABASE_URL -f api/migrations/001_tenants_webhooks.sql
psql $DATABASE_URL -f api/migrations/002_indexes.sql
psql $DATABASE_URL -f api/migrations/003_audit_log.sql

# Account + identity schema
psql $DATABASE_URL -f identity/migrations/001_initial_accounts.sql
```

### 5. Install dashboard dependencies

```bash
cd dashboard
npm install
cd ..
```

---

## Quick Start

### Run the API

```bash
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

OpenAPI docs: [http://localhost:8000/docs](http://localhost:8000/docs)  
Health check: [http://localhost:8000/health](http://localhost:8000/health)

### Run the dashboard

```bash
cd dashboard
npm run dev
```

Dashboard: [http://localhost:3000](http://localhost:3000)

### Run the test suite

```bash
# Unit tests only (no Docker required)
pytest -m "not integration and not smoke"

# Integration tests (requires docker-compose up)
pytest -m integration

# All tests with coverage
pytest --cov --cov-report=term-missing
```

### Produce test events

```bash
# Start the mock CRM signal generator
python -m ingestion.connectors.crm --mode mock --rate 10  # 10 events/sec

# Watch them land in Kafka
docker exec harmoni-kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic harmoni.crm.contact_activity \
  --from-beginning
```

---

## API Overview

All endpoints are under `/v1/`. JWT authentication is required (except `/health`).

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Liveness probe with circuit breaker status |
| `GET` | `/v1/accounts` | Paginated account list with score filters |
| `GET` | `/v1/accounts/{domain}` | Full account profile: scores, committee, active NBA |
| `GET` | `/v1/accounts/{domain}/fatigue` | Fatigue score + component breakdown |
| `GET` | `/v1/accounts/{domain}/intent` | Intent score + signal breakdown |
| `GET` | `/v1/accounts/{domain}/nba` | Current Next Best Action |
| `POST` | `/v1/accounts/{domain}/signals` | Ingest an ad-hoc signal |
| `POST` | `/v1/webhooks` | Register a partner webhook URL |
| `GET` | `/v1/webhooks` | List registered webhooks |
| `DELETE` | `/v1/webhooks/{id}` | Deregister a webhook |
| `POST` | `/v1/tenants` | Provision a new tenant (admin only) |

**Example — get an account profile:**

```bash
curl https://api.harmoni.io/v1/accounts/acme.com \
  -H "Authorization: Bearer ${PARTNER_JWT}" | jq '{
    fatigue: .fatigue.score,
    severity: .fatigue.severity,
    intent: .intent.intent_score,
    churn: .churn.churn_probability,
    nba: .current_nba.action_type
  }'
```

**Example — ingest a signal:**

```bash
curl -X POST https://api.harmoni.io/v1/accounts/acme.com/signals \
  -H "Authorization: Bearer ${PARTNER_JWT}" \
  -H "Content-Type: application/json" \
  -d '{
    "contact_email": "cto@acme.com",
    "signal_type": "pricing_page_view",
    "channel": "web",
    "metadata": {"page": "/pricing", "duration_seconds": 142}
  }'
```

---

## Webhook Events

Register a callback URL to receive real-time NBA events:

```bash
curl -X POST https://api.harmoni.io/v1/webhooks \
  -H "Authorization: Bearer ${PARTNER_JWT}" \
  -H "Content-Type: application/json" \
  -d '{
    "target_url": "https://hooks.your-app.com/harmoni",
    "event_types": ["nba.created", "fatigue.critical", "cooldown.set"]
  }'
```

All deliveries are signed with `X-Harmoni-Signature: sha256={hmac}` using your webhook's `signing_secret`. Verify signatures before processing.

---

## Environment Variables

Full reference in [`.env.example`](.env.example). Key variables:

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |
| `KAFKA_BOOTSTRAP_SERVERS` | Kafka broker address(es) |
| `API_SECRET_KEY` | JWT signing key (generate with `openssl rand -hex 32`) |
| `HARMONI_ADMIN_TOKEN` | Admin-only endpoint token |
| `WEBHOOK_SIGNING_SECRET` | HMAC key for outbound webhook signatures |
| `FEATURE_RL_ORCHESTRATOR` | Must remain `false` in production (see ADR 0004) |
| `CLEARBIT_API_KEY` | Optional: account enrichment |
| `OPENAI_API_KEY` | Optional: auxiliary signal embeddings |

---

## Project Structure

```
harmoni/
├── api/                    # FastAPI multi-tenant REST API
│   ├── routers/            # accounts, webhooks, tenants, health
│   ├── middleware/         # auth, audit, rate limiting, security headers
│   ├── migrations/         # SQL migration files
│   └── tests/
├── ingestion/              # Kafka CEP layer
│   ├── kafka/              # producers, consumers, schema registry client
│   ├── connectors/         # CRM, web, email, webinar source connectors
│   └── schemas/            # Avro schemas for all event types
├── identity/               # Account identity resolution engine
├── scoring/
│   ├── fatigue/            # Account Fatigue Score engine
│   ├── intent/             # Intent Network Model
│   └── churn/              # Churn Predictor
├── orchestrator/
│   ├── rules/              # Deterministic NBA rules engine (production)
│   ├── actions/            # CRM + webhook action dispatchers
│   └── rl/                 # RL experiments — isolated, never in prod paths
├── pipelines/
│   ├── dags/               # Airflow DAG definitions
│   └── dbt/                # dbt project (SCD Type 2 models)
├── dashboard/              # Next.js 14 RevOps / CMO dashboard
├── infra/
│   ├── terraform/          # Cloud infrastructure (VPC, Kafka, PostgreSQL)
│   ├── docker/             # PgBouncer config, Postgres init SQL
│   ├── alerting/           # Prometheus alert rules
│   └── load_tests/         # Locust + Kafka load test scripts
└── docs/
    ├── adr/                # Architecture Decision Records
    ├── runbooks/           # Incident response, partner onboarding
    └── backlog/            # Post-beta roadmap
```

---

## Key Architecture Decisions

| ADR | Decision |
|-----|----------|
| [0001](docs/adr/0001-account-key-is-normalized-domain.md) | Account key is the normalized email domain |
| [0002](docs/adr/0002-scd-type-2-for-account-history.md) | SCD Type 2 for immutable account history |
| [0003](docs/adr/0003-kafka-avro-schema-registry.md) | All Kafka messages require a registered Avro schema |
| [0004](docs/adr/0004-rl-orchestrator-behind-feature-flag.md) | RL orchestrator is feature-flagged and isolated |
| [0007](docs/adr/0007-owasp-security-hardening.md) | OWASP ASVS v4.0 Level 2 security hardening |

---

## Observability

- **Grafana dashboard**: `infra/grafana/dashboards/harmoni_overview.json` — import into Grafana pointed at your Prometheus datasource.
- **Alert rules**: `infra/alerting/rules.yml` — four Sev-1 PagerDuty triggers: Kafka consumer lag, Airflow DAG failure, API error rate, CRITICAL NBA dispatch failure.
- **Structured logs**: all services emit JSON logs. Ship to Loki or Datadog via Docker logging driver.
- **Health endpoint**: `GET /health` returns circuit breaker state for all external integrations.

---

## Runbooks

- [Incident Response (Sev-1)](docs/runbooks/incident_response.md)
- [Design Partner Onboarding](docs/runbooks/design_partner_onboarding.md)

---

## License

Proprietary. All rights reserved.
