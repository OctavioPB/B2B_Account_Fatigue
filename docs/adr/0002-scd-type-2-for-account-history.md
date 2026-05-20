# 0002: SCD Type 2 for Account and Committee Member History
**Status**: Accepted
**Date**: 2026-05-17

## Context

B2B accounts change over time: executives leave, companies are acquired, domains are aliased. If we overwrite account state, we lose the historical context needed to:
- Understand why a deal stalled (was the champion replaced?)
- Attribute intent signals to the right account version
- Audit fatigue score decisions that led to a lost deal

Options considered:
1. **Overwrite (SCD Type 1)** — simple but destroys history; non-auditable.
2. **Versioned rows with `valid_from`/`valid_to` (SCD Type 2)** — full history preserved; each state change creates a new row.
3. **Event sourcing** — complete audit trail but complex to query; overkill for this use case.

## Decision

All `Account` and `CommitteeMember` dimension tables use **SCD Type 2** implemented as dbt `snapshot` blocks.

Schema convention for every SCD Type 2 table:
- `dbt_scd_id` — surrogate key for this specific version row
- `dbt_updated_at` — when this row was last confirmed current
- `dbt_valid_from` — timestamp when this record version became active
- `dbt_valid_to` — timestamp when superseded (NULL = current version)
- `is_current` — boolean convenience column (WHERE is_current = TRUE for latest)

The `Account` surrogate key is `{normalized_domain}::{dbt_valid_from}`. The business key is always `normalized_domain`.

## Consequences

- **Hard rule**: Never `UPDATE` or `DELETE` rows in SCD Type 2 dimension tables. All mutations are new inserts. This is enforced by dbt immutability tests on every DAG execution.
- **Positive**: Full audit trail of account state changes; retroactive analysis is always accurate.
- **Positive**: Intent signals can be joined to the account version that was current _at the time_ the signal was emitted.
- **Negative**: Queries for current state require a `WHERE is_current = TRUE` filter; forgetting it produces fan-out joins. dbt intermediate models should always pre-filter to current state.
- **Operational**: The dbt snapshot strategy uses `timestamp` (not `check`), keyed on `updated_at` from source systems.
