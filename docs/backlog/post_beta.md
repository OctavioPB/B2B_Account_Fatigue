# Post-Beta Backlog — Sprint 11+
**System**: harmoni Revenue Intelligence Platform  
**Version**: 1.0 — Sprint 10  
**Last updated**: 2026-05-17

This document captures all work intentionally deferred from the beta launch (Sprint 10). Items are triaged by value tier and rough effort. Priorities should be re-evaluated after the first two weeks of design-partner feedback.

---

## Tier 1 — High Value, Next Sprint

### S11-01: RL-Based NBA Orchestrator (Production Promotion)
**What**: Graduate the RLlib policy in `orchestrator/rl/` from research to a shadow-mode A/B test against the deterministic rules engine.  
**Why**: Deterministic rules cannot learn from feedback; RL closes the loop on which NBAs actually prevent churn.  
**Gate**: Offline evaluation benchmark must show ≥ 5% improvement in simulated churn-prevention rate vs. rules engine before any live traffic is split.  
**Flag**: `FEATURE_RL_ORCHESTRATOR=true` — already wired, only needs shadow-mode harness and evaluation pipeline.  
**Effort**: L (3–4 weeks including eval pipeline)  
**Owner**: Data team

---

### S11-02: LinkedIn Organic Signal Connector
**What**: Ingest LinkedIn company page activity (follower growth, post engagement, job posting velocity) as `IntentSignal`s via the LinkedIn Marketing API.  
**Why**: Job posting velocity (especially for roles in the buyer's toolchain) is one of the strongest leading indicators of budget unlock and committee formation.  
**Avro schema**: `harmoni.linkedin.company_activity` — must be registered before any messages are produced.  
**Effort**: M (1–2 weeks)  
**Owner**: Ingestion team

---

### S11-03: G2 / Bombora Intent Data Integration
**What**: Pull third-party intent signals from G2 Buyer Intent API and Bombora Company Surge into the CEP pipeline.  
**Why**: First-party signals alone miss accounts researching competitors. Third-party intent data dramatically improves recall on in-market accounts.  
**Notes**: Requires partnership agreements for G2 and Bombora APIs. Data must be schema-validated and attributed to source (`signal_source: "g2" | "bombora"`) before being written to ClickHouse.  
**Effort**: M (2 weeks including contract/API provisioning)  
**Owner**: Data team + CS (for vendor contracts)

---

### S11-04: HubSpot Native Embedded App
**What**: Build a HubSpot CRM Card that surfaces harmoni fatigue score, NBA recommendation, and cooldown status directly on the HubSpot contact/company record — without requiring the partner to switch to the harmoni dashboard.  
**Why**: The #1 design-partner friction point is context switching. Native embedding removes the workflow gap.  
**Effort**: M (2 weeks)  
**Owner**: Platform team  
**Dependency**: HubSpot public app review (allow 2 weeks for approval)

---

## Tier 2 — High Value, Plan for Sprint 12

### S12-01: Salesforce Managed Package (GA)
**What**: Complete the Salesforce managed package started in Sprint 8 (AppExchange ID: TBD). Surface harmoni NBA as a custom Salesforce component on the Opportunity record.  
**Why**: Enterprise design partners use Salesforce; HubSpot-only reach limits TAM.  
**Effort**: L (3–4 weeks, includes AppExchange security review)  
**Owner**: Platform team

---

### S12-02: Slack / Microsoft Teams Native Integration
**What**: Push NBA recommendations and CRITICAL fatigue alerts directly into partner Slack channels or Teams threads — not just outbound webhooks.  
**Why**: Webhooks require partner engineering effort to consume. Native messaging integrations work out of the box for non-technical RevOps users.  
**Implementation notes**:  
  - Slack: OAuth 2.0 bot token flow, `chat.postMessage` with Block Kit layout  
  - Teams: Incoming Webhook connector + Adaptive Cards  
  - Both integrations must go through `circuit_breakers.py` (breakers already exist for `slack`)  
**Effort**: M (2 weeks per channel)  
**Owner**: Platform team

---

### S12-03: Self-Serve Tenant Onboarding
**What**: Replace the manual 8-step onboarding runbook with a guided in-app flow: sign up → connect CRM → seed accounts → validate scores. No CS/SE involvement required for standard onboarding.  
**Why**: Manual onboarding caps partner growth at CS bandwidth. Self-serve is a prerequisite for GA.  
**Effort**: XL (6–8 weeks, touches API, dashboard, and email flows)  
**Owner**: Product + Platform + Dashboard teams

---

### S12-04: Webhook Delivery Dashboard
**What**: Surface webhook health (delivery success rate, recent failures, retry queue depth) in the Settings page for each partner tenant.  
**Why**: Partners currently have no visibility into whether their webhooks are failing. Reduces support tickets.  
**Effort**: S (3–5 days — API already has `webhook_delivery_log`, just needs a frontend panel)  
**Owner**: Dashboard team

---

## Tier 3 — Strategic, Sprint 13+

### S13-01: SOC 2 Type II Audit Preparation
**What**: Engage a SOC 2 auditor. Implement: continuous evidence collection from audit log, access control review, change management documentation, incident response drill.  
**Why**: Enterprise buyers and data-sensitive design partners (financial services, healthcare) will block procurement without SOC 2 Type II.  
**Notes**: The audit log (`003_audit_log.sql`, `AuditLogMiddleware`) and OWASP hardening (Sprint 10) are prerequisites — they're done. Remaining gap is people/process: access reviews, HR controls, vendor management.  
**Effort**: XL (3–6 months elapsed time)  
**Owner**: CTO + external auditor

---

### S13-02: Multi-Language Dashboard (i18n)
**What**: Internationalise the Next.js dashboard for EN, DE, FR (Phase 1). Support for partner locale in score explanations and NBA action labels.  
**Why**: Two design partners are headquartered in EMEA and have RevOps teams that prefer German or French UI.  
**Implementation**: `next-intl` library, message catalogs in `dashboard/messages/`, locale detection from `Accept-Language` header via Edge middleware.  
**Effort**: M (2–3 weeks for EN/DE/FR)  
**Owner**: Dashboard team

---

### S13-03: Buying Committee Org Chart Visualisation
**What**: Visual graph of a committee's stakeholder network: role nodes, engagement heat, relationship lines (reports-to, influences).  
**Why**: CMO users want to see the committee holistically, not just aggregated scores. This is a key differentiator vs. traditional ABM platforms that show contact lists.  
**Implementation notes**: D3.js or `@visx/network`. Data from `committee_members` + SCD Type 2 snapshots. Strict account-first rendering — no contact PII surfaced without explicit role/name consent.  
**Effort**: L (3–4 weeks)  
**Owner**: Dashboard team + Data team

---

### S13-04: Deal Room Integration (Notion / Confluence)
**What**: Push account health summaries (fatigue trend, NBA history, committee coverage) into a Notion or Confluence page automatically when a deal enters a target stage.  
**Why**: AEs maintain deal rooms in Notion/Confluence; embedding live harmoni data reduces prep time for QBRs and exec briefings.  
**Effort**: M (2 weeks per integration)  
**Owner**: Platform team

---

## Known Technical Debt

| Item | File(s) | Impact | Sprint |
|------|---------|--------|--------|
| Stub account data in `accounts.py` — replace with real DB reads | `api/routers/accounts.py` | Correctness | S11 |
| In-memory webhook store — replace with DB-backed store | `api/routers/webhooks.py` | Durability | S11 |
| Airflow DAG uses `LocalExecutor` — migrate to `CeleryExecutor` for prod scale | `infra/` | Scalability | S12 |
| ClickHouse schema not yet created | `pipelines/` | Analytics queries | S11 |
| `scripts/issue_jwt.py` referenced in onboarding runbook but not yet written | `scripts/` | Onboarding blocker | S11 |
| `scripts/seed_accounts.py` referenced in onboarding runbook but not yet written | `scripts/` | Onboarding blocker | S11 |
| `@vitejs/plugin-react` missing from `package.json` devDependencies | `dashboard/package.json` | Test suite broken | S11 |
| TLS commented out in `pgbouncer.ini` | `infra/docker/pgbouncer.ini` | Security (prod) | S11 |
| Salesforce AppExchange ID is TBD | `docs/runbooks/design_partner_onboarding.md` | Partner onboarding | S12 |

---

## Deferred Experiments (Do Not Promote Without Evaluation)

- **LLM-generated NBA explanations**: Use GPT-4o to generate natural-language rationale for each NBA recommendation. High engagement value but latency risk and cost-per-call must be modelled. Behind `FEATURE_NBA_EXPLANATIONS=false`.
- **Predictive cooldown duration**: Train a regression model on historical cooldown outcomes to set dynamic cooldown lengths (rather than fixed rules). Requires ≥ 6 months of production data.
- **Account similarity clustering**: Cluster accounts by signal pattern to identify "accounts like this one went cold after X" — proactive warning before fatigue scores spike.
