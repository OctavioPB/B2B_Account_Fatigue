# harmoni dbt Project

Data transformation layer for the harmoni Revenue Intelligence platform.

## Model Architecture

```
sources (raw PostgreSQL tables)
    └── staging/   (stg_*)    — cast, rename, light filter       → PostgreSQL views
         └── intermediate/ (int_*) — cross-source joins, signal unification → PostgreSQL incremental
              └── marts/
                   ├── dimensions/ (dim_*) — current-state views over SCD snapshots → PostgreSQL views
                   └── facts/      (fct_*) — hourly aggregations                   → ClickHouse incremental

snapshots/ (snap_*)  — SCD Type 2 via dbt snapshot                 → PostgreSQL snapshots schema
```

## Quick Start

```bash
# Install dependencies
pip install dbt-postgres dbt-clickhouse

# Copy and configure profiles
cp profiles.yml.example ~/.dbt/profiles.yml

# Install dbt packages
dbt deps

# Run staging + intermediate + snapshot + marts (PostgreSQL target)
dbt run --target dev

# Run fact models on ClickHouse
dbt run --target clickhouse --select marts.facts.*

# Run all tests
dbt test

# Generate and serve docs
dbt docs generate && dbt docs serve
```

## Source Systems

| Source table | Source system | dbt staging model |
|---|---|---|
| `raw_web_pageviews` | Web pixel / server logs | `stg_web_pageviews` |
| `raw_email_engagements` | HubSpot / Outreach / Mailchimp | `stg_email_engagements` |
| `raw_crm_contact_activities` | HubSpot / Salesforce / Pipedrive | `stg_crm_contact_activities` |
| `raw_webinar_attendances` | Zoom / GoToWebinar | `stg_webinar_attendances` |
| `accounts` | Identity resolution (Sprint 3) | `stg_accounts` |
| `committee_members` | Identity resolution (Sprint 3) | `stg_committee_members` |

## SCD Type 2 Snapshots

`snap_accounts` and `snap_committee_members` track every change to the
corresponding operational tables using `strategy=timestamp` on `updated_at`.

**Immutability hard rule (ADR 0002, CLAUDE.md Section 10)**: Never `UPDATE`
or `DELETE` rows in the `snapshots` schema. Historical rows are immutable.
The `assert_no_scd_mutations` singular test enforces this on every DAG run.

## dbt Tests

- `not_null` and `unique` on all surrogate and natural keys
- `accepted_values` on all enum columns (source_system, signal_strength, etc.)
- `assert_no_scd_mutations` — custom: verifies no historical snapshot rows were mutated
- `assert_snapshot_has_current_row` — custom: verifies every entity has exactly one current row

## Meta Tag Requirements

All models must carry:
```yaml
meta:
  owner: "data-engineering"
  source: "<source_system>"
  refresh_cadence: "hourly"   # realtime | hourly | daily
```

## Naming Conventions

| Layer | Prefix | Example |
|---|---|---|
| Staging | `stg_` | `stg_web_pageviews` |
| Snapshot | `snap_` | `snap_accounts` |
| Intermediate | `int_` | `int_account_signals` |
| Fact | `fct_` | `fct_account_signal_hourly` |
| Dimension | `dim_` | `dim_account` |
