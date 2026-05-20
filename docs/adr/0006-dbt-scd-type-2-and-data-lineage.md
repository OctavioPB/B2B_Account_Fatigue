# 0006: dbt SCD Type 2 Snapshots and Data Lineage Strategy
**Status**: Accepted
**Date**: 2026-05-17

## Context

harmoni's value proposition depends on accurate historical tracking of account and committee-member state. Firmographic changes (company rebrand, acquisition), role changes (new CFO, title update), and committee composition changes (member joins or leaves) are business-critical events — losing that history degrades Intent Network Model accuracy and removes the audit trail required for compliance.

Additionally, four Kafka signal sources (web, email, CRM, webinar) produce events at different cadences and schemas. Downstream scoring models (Sprint 5 onward) need a clean, consistent signal layer that abstracts source-system differences.

Three options were considered for historical tracking:
1. **Application-level versioning** — application code manages `valid_from`/`valid_to` columns directly in PostgreSQL.
2. **dbt SCD Type 2 snapshots** — dbt manages historical rows automatically using `strategy=timestamp`, driven by `updated_at` changes.
3. **Event sourcing** — all state changes stored as immutable events; current state reconstructed by replaying event log.

## Decision

Use **dbt SCD Type 2 snapshots** (`strategy=timestamp`) for `Account` and `CommitteeMember` history, and a **layered dbt model architecture** (Staging → Intermediate → Mart) for all signal data.

### Snapshot strategy

Both `snap_accounts` and `snap_committee_members` use:
- `unique_key = 'id'` — matches PostgreSQL primary key
- `strategy = 'timestamp'` — detects changes via `updated_at` column
- `target_schema = 'snapshots'` — isolated from operational tables

dbt adds four columns to each snapshot table:
| Column | Meaning |
|---|---|
| `dbt_scd_id` | UUID for this specific snapshot row |
| `dbt_updated_at` | When dbt last processed this row |
| `dbt_valid_from` | Start of this version's validity window |
| `dbt_valid_to` | End of validity window; `NULL` = currently active |

**Immutability invariant (Hard Rule #3 in `CLAUDE.md`)**: Once `dbt_valid_to` is set (row is historical), no business column on that row may change. This is enforced by:
1. Never running `UPDATE` on snapshot tables outside dbt
2. A custom singular dbt test `assert_no_scd_mutations` that returns non-zero rows on violation
3. The Airflow DAG runs this test after every `dbt snapshot` invocation

### Model layer convention

| Layer | Prefix | Materialization | Location | Purpose |
|---|---|---|---|---|
| Staging | `stg_` | `view` | PostgreSQL | Type casting, rename, light filtering |
| Snapshots | `snap_` | `snapshot` | PostgreSQL (`snapshots` schema) | SCD Type 2 history |
| Intermediate | `int_` | `incremental` | PostgreSQL | Cross-source joins, signal unification |
| Marts / Facts | `fct_` | `incremental` | ClickHouse | Hourly aggregates for scoring queries |
| Marts / Dims | `dim_` | `view` | PostgreSQL | Current-row views over snapshot tables |

### ClickHouse for fact tables

High-throughput aggregation queries (Sprint 5 scoring engine) run against ClickHouse, not PostgreSQL. `fct_account_signal_hourly` and `fct_committee_engagement` are written to ClickHouse using the `dbt-clickhouse` adapter under the `clickhouse` profile target. The Airflow DAG calls `dbt run --target clickhouse --select marts.fct_*` as a separate step after the PostgreSQL models complete.

### Meta tag requirement

All models must carry:
```yaml
meta:
  owner: "data-engineering"
  source: "<source_system>"
  refresh_cadence: "hourly"    # or "realtime" / "daily"
```

This is validated by the dbt `meta_required` macro and checked in CI.

## Consequences

- **Positive**: Full audit trail for every account and member change; time-travel queries are trivial (`WHERE dbt_valid_to IS NULL` for current, `WHERE dbt_valid_from <= :ts AND (dbt_valid_to > :ts OR dbt_valid_to IS NULL)` for point-in-time).
- **Positive**: Source-system abstractions in staging models mean scoring logic never reads raw tables directly — schema changes in connectors only require staging model updates.
- **Positive**: ClickHouse fact tables give the scoring engine sub-second aggregation over millions of signal rows.
- **Negative**: dbt snapshot runs add ~30 seconds to the hourly Airflow DAG. Acceptable given the 60-minute cadence.
- **Operational**: Never `UPDATE` or `DELETE` rows in `snapshots.*` schema. Add to onboarding docs and enforce via PostgreSQL row-level permissions in production.
- **Operational**: Monitor `dbt test` failure rate. A failing `assert_no_scd_mutations` test is a Sev-1 incident.
