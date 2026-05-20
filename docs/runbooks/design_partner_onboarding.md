# Design Partner Onboarding Runbook
**Audience**: Customer Success / Solutions Engineer  
**Version**: 1.0 — Sprint 10

---

## Overview

This runbook covers the end-to-end steps to onboard a design-partner tenant onto harmoni, validate that their account scores are computing correctly, and connect their first data source.

**Time required**: ~90 minutes per partner (plus async data validation overnight)

---

## Prerequisites

Before starting, confirm with the partner:
- [ ] CRM system identified (HubSpot / Salesforce)
- [ ] At least 10 target accounts nominated with known domains
- [ ] Technical contact available for webhook integration step
- [ ] NDA signed; data processing agreement in place

Internal prerequisites:
- [ ] Production database is healthy (`kubectl get pods -n harmoni-prod`)
- [ ] `HARMONI_ADMIN_TOKEN` rotated and available in 1Password vault `prod/harmoni-admin-token`
- [ ] Slack channel `#dp-{partner-slug}` created and partner invited

---

## Step 1 — Provision the Tenant

```bash
# Replace slug, display_name, and plan with partner values.
# Slug must match the domain slug convention: company-name (lowercase, hyphens)

curl -s -X POST https://api.harmoni.io/v1/tenants \
  -H "Authorization: Bearer ${HARMONI_ADMIN_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "slug": "acme-corp",
    "display_name": "Acme Corporation",
    "plan": "growth",
    "rate_limit_rpm": 120
  }' | jq .
```

**Expected output**:
```json
{
  "id": "<uuid>",
  "slug": "acme-corp",
  "schema_name": "tenant_acme_corp",
  "plan": "growth",
  "is_active": true
}
```

Copy the `id` (tenant UUID) — needed for JWT issuance.

---

## Step 2 — Issue Partner JWT

```bash
# Uses the JWT signing script in scripts/issue_jwt.py
# Requires: API_SECRET_KEY from prod secrets

python scripts/issue_jwt.py \
  --tenant-id "<uuid from step 1>" \
  --slug "acme-corp" \
  --schema "tenant_acme_corp" \
  --plan "growth" \
  --rpm 120 \
  --expires-hours 720   # 30 days
```

Share the token securely via 1Password shared vault — **never over email or Slack**.

---

## Step 3 — Run Tenant Schema Migration

```bash
# Alembic creates the tenant's isolated PostgreSQL schema
alembic -x tenant=tenant_acme_corp upgrade head

# Verify schema exists
psql $DATABASE_URL -c "\dn" | grep tenant_acme_corp
```

---

## Step 4 — Load Seed Accounts

Partners provide a CSV: `domain, display_name, industry, arr_usd`.

```bash
python scripts/seed_accounts.py \
  --tenant-schema tenant_acme_corp \
  --csv partner_accounts.csv
```

Verify:
```bash
curl -s https://api.harmoni.io/v1/accounts \
  -H "Authorization: Bearer ${PARTNER_JWT}" | jq '.total'
# Should match row count in CSV
```

---

## Step 5 — Connect CRM Webhook

### HubSpot
1. Partner navigates to **HubSpot → Settings → Integrations → Webhooks**
2. Add new webhook: `https://api.harmoni.io/v1/accounts/{domain}/signals`
3. Subscribe to: `contact.propertyChange`, `deal.creation`, `deal.propertyChange`
4. Test with HubSpot's "Send test" button — confirm 202 response in harmoni logs

### Salesforce (alternative)
1. Partner installs the harmoni managed package (AppExchange ID: TBD)
2. Configure outbound messaging rule → harmoni API endpoint

Validation:
```bash
# Watch signal ingestion in real time
kubectl logs -f deploy/harmoni-api -n harmoni-prod | grep "Signal ingested"
```

---

## Step 6 — Register Partner Webhook for NBA Events

Partner registers their callback URL for real-time NBA notifications:

```bash
curl -s -X POST https://api.harmoni.io/v1/webhooks \
  -H "Authorization: Bearer ${PARTNER_JWT}" \
  -H "Content-Type: application/json" \
  -d '{
    "target_url": "https://hooks.partner.com/harmoni",
    "description": "Acme Corp NBA notifications",
    "event_types": ["nba.created", "fatigue.critical", "cooldown.set"]
  }'
```

Share the `signing_secret` from the response with the partner's technical contact.

---

## Step 7 — Validate First Account Scores

Wait for the next pipeline runs:
- Intent + Churn scores: next 4-hour boundary
- Fatigue scores: within 30 minutes

```bash
# Check score freshness for a known domain
curl -s https://api.harmoni.io/v1/accounts/acme.com \
  -H "Authorization: Bearer ${PARTNER_JWT}" | jq '{
    fatigue: .fatigue.score,
    severity: .fatigue.severity,
    intent: .intent.intent_score,
    churn: .churn.churn_probability,
    nba: .current_nba.action_type
  }'
```

**Acceptance criteria**:
- All three scores populated (non-null)
- At least one account has fatigue severity not LOW (confirms signal ingestion is working)
- NBA action type matches expectations given fatigue/intent state

---

## Step 8 — Send Welcome Package

- [ ] Share dashboard URL: `https://app.harmoni.io` with partner JWT
- [ ] Send scoring methodology 1-pager (in `docs/partner_materials/`)
- [ ] Schedule weekly 30-min feedback call (recurring, in partner's calendar)
- [ ] Add partner to `#beta-partners` Slack channel
- [ ] Send NPS survey link (first survey at day 7)

---

## Escalation

| Issue | Owner | Contact |
|-------|-------|---------|
| Tenant provisioning failure | Platform team | `#platform-oncall` |
| Score not computing | Data team | `#data-oncall` |
| Webhook delivery failure | Platform team | PagerDuty alert auto-fires |
| Partner data question | CS | `#dp-{partner-slug}` |

---

## Rollback

If onboarding must be reversed:
```bash
# Deactivate tenant (preserves data for audit)
curl -X PATCH https://api.harmoni.io/v1/tenants/{id} \
  -H "Authorization: Bearer ${HARMONI_ADMIN_TOKEN}" \
  -d '{"is_active": false}'

# Drop schema (destructive — requires explicit approval from CTO)
psql $DATABASE_URL -c "DROP SCHEMA tenant_acme_corp CASCADE;"
```
