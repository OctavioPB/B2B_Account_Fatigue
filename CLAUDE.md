# CLAUDE.md — Agent Constitution
## B2B Account Fatigue & Committee Journey Harmonizer
### Codename: `harmoni`

> This file is the authoritative agent constitution for all Claude Code interactions in this repository.
> Read it entirely before touching any file. All rules here are non-negotiable.
> **UI and visual design decisions live exclusively in [`BRAND.md`](./BRAND.md).**

---

## 1. Project North Star

**harmoni** solves a critical ABM (Account-Based Marketing) coordination failure: B2B buying decisions are made by committees (CFO, CTO, COO, etc.), yet existing automation tools (HubSpot, Marketo) treat each stakeholder as an isolated lead. The result is cognitive overload, misaligned messaging, and lost deals.

harmoni evaluates the **collective journey health** of a target account — not individual contacts — and orchestrates the **Next Best Action (NBA)** for marketing and sales teams based on the account's consolidated fatigue and intent state.

**The product is positioned as a Revenue Intelligence & Deal Protection platform, not a contact surveillance tool.** This distinction is a hard go-to-market rule; it must never be undermined by feature naming, API labels, or documentation.

---

## 2. Repository Structure

```
harmoni/
├── CLAUDE.md                  # This file — agent constitution
├── BRAND.md                   # UI/design decisions — see Section 9
├── PLAN.md                    # Sprint roadmap
├── .env.example               # All env vars documented, no secrets
│
├── ingestion/                 # CEP event ingestion layer
│   ├── kafka/                 # Kafka producers & topic configs
│   ├── connectors/            # Source connectors (CRM, web, email, webinar)
│   └── schemas/               # Avro/JSON schemas for all events
│
├── pipelines/                 # Airflow DAGs and dbt models
│   ├── dags/                  # Airflow DAG definitions
│   ├── dbt/                   # dbt project (SCD Type 2, dimensions)
│   └── transforms/            # Python transformation scripts
│
├── identity/                  # Account identity resolution engine
│   ├── resolver.py            # Domain-based entity linking logic
│   └── tests/
│
├── scoring/                   # Core intelligence layer
│   ├── fatigue/               # Account Fatigue Score engine
│   ├── intent/                # Intent Network Modeling (signal consolidation)
│   └── churn/                 # Churn Predictor (account-level)
│
├── orchestrator/              # Next Best Action (NBA) engine
│   ├── rules/                 # Dynamic rule definitions
│   ├── rl/                    # Reinforcement learning experiments (isolated)
│   └── actions/               # Action dispatch integrations
│
├── api/                       # FastAPI multi-tenant REST API
│   ├── routers/
│   ├── middleware/
│   ├── models/                # Pydantic schemas
│   └── tests/
│
├── dashboard/                 # Next.js 14 RevOps/CMO frontend
│   ├── app/                   # App Router pages
│   ├── components/
│   └── lib/
│
├── infra/                     # Terraform, Docker, Helm charts
│   ├── terraform/
│   └── docker/
│
└── docs/                      # Architecture decision records (ADRs)
    └── adr/
```

---

## 3. Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| Event Streaming | Apache Kafka | Complex Event Processing (CEP), real-time signal unification |
| Workflow Orchestration | Apache Airflow | Hourly pipeline runs, DAG management |
| Data Transformation | dbt (Data Build Tool) | SCD Type 2 models, data lineage, dimension tables |
| Operational Database | PostgreSQL 15 | Account state, NBA triggers, multi-tenant config |
| Analytics Store | ClickHouse | High-throughput aggregated scoring queries |
| Real-time State | Redis | Session-level fatigue counters, NBA lock/cooldown |
| ML / Scoring | Python + scikit-learn | Fatigue scoring, churn prediction |
| RL Experimentation | Python + RLlib | Next Best Action policy learning (isolated `rl/` module) |
| Backend API | FastAPI | Multi-tenant REST API, webhook dispatch |
| Frontend | Next.js 14 (App Router) | RevOps / CMO dashboard — see BRAND.md |
| Identity Resolution | Custom Python | Domain-based entity linking across fragmented sources |
| Infrastructure | Terraform + Docker | Reproducible infra, containerized services |

> All ML experiments in `orchestrator/rl/` are research modules.
> They must never be imported from production code paths without a feature flag.

---

## 4. Core Domain Concepts

These terms are canonical. Use them exactly — in code, comments, API contracts, and documentation.

### 4.1 Buying Committee (`BuyingCommittee`)
The set of individual stakeholders (`CommitteeMember`) at a target account who collectively influence a purchase decision. Identified by their company domain (e.g., `acme.com`). This is the primary unit of analysis — never a single contact.

### 4.2 Account (`Account`)
The target company entity, keyed by **normalized email domain**. All signals, scores, and actions roll up to this entity. Accounts are tracked with SCD Type 2 to handle org changes (mergers, executive turnover).

### 4.3 Intent Signal (`IntentSignal`)
A discrete behavioral event emitted by any `CommitteeMember`: email open, pricing page visit, webinar attendance, video view, CRM note, etc. Signals are **weak** individually and require consolidation via Intent Network Modeling.

### 4.4 Account Fatigue Score (`AccountFatigueScore`)
A composite score (0–100) representing the collective cognitive load of a `BuyingCommittee`. A high score triggers cooldown protocols. Computed from: outreach frequency, open/response decay rate, unsubscribe signals, and engagement recency.

### 4.5 Intent Network Model (`IntentNetworkModel`)
The ML subsystem that aggregates weak `IntentSignal`s from multiple `CommitteeMember`s to produce a single account-level **Intent Score** and **Churn Probability**. Signals are weighted by member role and recency.

### 4.6 Churn Predictor (`ChurnPredictor`)
Account-level binary classifier predicting deal abandonment risk within a rolling 30-day window. Output feeds the NBA orchestrator.

### 4.7 Next Best Action (`NextBestAction`)
The system-recommended marketing or sales action for a target `Account`, given its current `AccountFatigueScore`, `IntentScore`, and `ChurnProbability`. Actions include: cooldown, nurture sequence, executive escalation, pricing conversation trigger, etc.

### 4.8 Action Cooldown (`ActionCooldown`)
A time-based lock applied to an `Account` or individual `CommitteeMember` to prevent over-contact. Stored in Redis. Cooldown durations are dynamic and driven by the NBA orchestrator.

### 4.9 Complex Event Processing (`CEP`)
The Kafka-based pipeline that unifies fragmented real-time signals from heterogeneous sources under the canonical `Account` key (domain). CEP events are always schema-validated before being written to any store.

### 4.10 SCD Type 2 (`SCDType2`)
Slowly Changing Dimension Type 2: the dbt pattern used to track historical state of `Account` and `CommitteeMember` records. Every change (role change, company merge) creates a new row with `valid_from` / `valid_to` timestamps. Never overwrite historical records.

---

## 5. Python Coding Standards

- **Python version**: 3.11+
- **Formatter**: `ruff format` (replaces black)
- **Linter**: `ruff check` — zero warnings policy
- **Type hints**: Required on all function signatures, no `Any` unless justified with a comment
- **Docstrings**: Google-style on all public functions and classes
- **Testing**: `pytest` with `pytest-asyncio` for async paths; minimum 80% coverage per module
- **Dependency management**: `uv` + `pyproject.toml`; never `requirements.txt` in new code
- **Async**: Use `asyncio` throughout FastAPI routes; no blocking calls in async context
- **Error handling**: Custom exception classes in `api/exceptions.py`; never raise bare `Exception`
- **Secrets**: Never hardcode. Always load from env via `pydantic-settings` `BaseSettings`

```python
# Canonical account key pattern — always normalize before lookup
def normalize_domain(email_or_domain: str) -> str:
    """Extract and lowercase the domain portion of an email or domain string."""
    domain = email_or_domain.split("@")[-1].strip().lower()
    return domain
```

---

## 6. TypeScript / Next.js Coding Standards

> All visual and component-level decisions are in `BRAND.md`.
> This section covers structural and logic-layer rules only.

- **TypeScript**: Strict mode enabled (`"strict": true`), no `any`
- **Component pattern**: Server Components by default; Client Components only when interactivity requires it (`"use client"` at the top, never sprinkled arbitrarily)
- **State management**: `zustand` for client state; React Query (`@tanstack/query`) for server state
- **API calls from frontend**: Always through `lib/api/` abstraction layer — never raw `fetch` in components
- **Types**: Co-located in `types/` or alongside the module they describe; shared types in `lib/types/`
- **Naming**: Components `PascalCase`, hooks `useCamelCase`, utilities `camelCase`
- **Testing**: `vitest` + `@testing-library/react`

---

## 7. Data & Pipeline Standards

- **Kafka topics**: Named `harmoni.{source}.{event_type}` (e.g., `harmoni.crm.contact_activity`)
- **Avro schemas**: All Kafka messages must have a registered Avro schema in `ingestion/schemas/`
- **dbt models**: Staging → Intermediate → Mart layer convention; `stg_`, `int_`, `fct_`, `dim_` prefixes
- **SCD Type 2**: Use dbt `snapshot` blocks for all `Account` and `CommitteeMember` dimension tables
- **Airflow DAGs**: One DAG per logical pipeline; no cross-DAG imports; use `TaskFlow API` style
- **Idempotency**: Every pipeline step must be idempotent — re-running must produce the same result
- **Data lineage**: dbt `meta` tags required on all models; document owner, source system, and refresh cadence

---

## 8. Environment Variables

Document all env vars in `.env.example`. Never add a var without an entry there.

```bash
# --- Database ---
DATABASE_URL=postgresql://user:pass@localhost:5432/harmoni
CLICKHOUSE_HOST=localhost
CLICKHOUSE_PORT=9000
REDIS_URL=redis://localhost:6379/0

# --- Kafka ---
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
KAFKA_SCHEMA_REGISTRY_URL=http://localhost:8081

# --- ML / AI ---
OPENAI_API_KEY=sk-...            # Used for embedding auxiliary signals
OPENAI_EMBEDDING_MODEL=text-embedding-3-small

# --- Airflow ---
AIRFLOW__CORE__EXECUTOR=LocalExecutor
AIRFLOW__DATABASE__SQL_ALCHEMY_CONN=postgresql://...

# --- API ---
API_SECRET_KEY=...               # FastAPI JWT signing key
API_ALLOWED_ORIGINS=http://localhost:3000

# --- Multi-tenancy ---
TENANT_ISOLATION_MODE=schema     # Options: schema | database

# --- Feature Flags ---
FEATURE_RL_ORCHESTRATOR=false    # Never enable in prod without full eval
```

---

## 9. UI & Design Decisions → BRAND.md

**All visual, branding, and UX decisions are exclusively governed by [`BRAND.md`](./BRAND.md).**

This includes and is not limited to:
- Color palette, typography, spacing tokens
- Component library selection
- Dashboard layout and information hierarchy
- Chart and data visualization style
- Empty states, loading skeletons, error UI
- Logo, wordmark, and iconography
- Email and outreach template design
- Copy tone and microcopy guidelines

**Hard rule**: Do not make any UI decision — even a color or a font size — without first checking `BRAND.md`. If `BRAND.md` does not yet cover a case, add the decision to `BRAND.md` before implementing it. Never embed visual decisions in component files without a corresponding `BRAND.md` entry.

---

## 10. Hard Rules

These rules are absolute. No exception, no override, no creative reframing.

1. **Positioning rule**: The product is a **Revenue Intelligence & Deal Protection** platform. Never describe it as a contact tracker, behavior surveillance system, or lead scoring tool in any user-facing surface, API contract, or documentation. If in doubt, check with the product owner before naming anything.

2. **Account-first rule**: Every model, query, and API response must roll up to the `Account` entity (domain key). Returning contact-level data without account context is a schema violation.

3. **SCD Type 2 immutability**: Never `UPDATE` or `DELETE` rows in SCD Type 2 dimension tables. Create new rows. Historical truth is inviolable.

4. **RL isolation rule**: Reinforcement learning code lives only in `orchestrator/rl/`. It must be behind the `FEATURE_RL_ORCHESTRATOR=false` flag. Production NBA actions use the deterministic rules engine until the RL policy passes offline evaluation benchmarks.

5. **Schema-first for Kafka**: No Kafka message may be produced without a registered Avro schema. The schema registry is the source of truth for all event contracts.

6. **No secrets in code**: No API key, password, or token may appear in source code or git history. Use `.env` + `pydantic-settings`. Violation triggers immediate secret rotation.

7. **BRAND.md gate**: No UI component ships without a corresponding entry in `BRAND.md`. See Section 9.

---

## 11. Architecture Decision Records (ADRs)

All significant technical decisions must be recorded in `docs/adr/` using the format:

```
docs/adr/
└── NNNN-short-title.md
```

Template:
```markdown
# NNNN: [Short Title]
**Status**: [Proposed | Accepted | Deprecated]
**Date**: YYYY-MM-DD
## Context
## Decision
## Consequences
```

Current ADRs to create on project init:
- `0001-account-key-is-normalized-domain.md`
- `0002-scd-type-2-for-account-history.md`
- `0003-kafka-avro-schema-registry.md`
- `0004-rl-orchestrator-behind-feature-flag.md`
