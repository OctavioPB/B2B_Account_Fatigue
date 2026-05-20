/*
    Singular test: assert_no_scd_mutations
    =========================================================================
    Verifies the SCD Type 2 immutability invariant (ADR 0002, CLAUDE.md §10):

    For any historical snapshot row (dbt_valid_to IS NOT NULL), the validity
    window must be strictly positive: dbt_valid_from < dbt_valid_to.

    A violation means a historical row was modified AFTER it was closed —
    this indicates a dbt snapshot bug or an unauthorised direct UPDATE on the
    snapshots schema, either of which is a Sev-1 incident.

    Returns non-zero rows on failure (dbt test convention).
*/

-- Check snap_accounts
select
    'snap_accounts'     as snapshot_table,
    dbt_scd_id,
    id                  as entity_id,
    dbt_valid_from,
    dbt_valid_to
from {{ ref('snap_accounts') }}
where dbt_valid_to is not null
  and dbt_valid_from >= dbt_valid_to

union all

-- Check snap_committee_members
select
    'snap_committee_members' as snapshot_table,
    dbt_scd_id,
    id                       as entity_id,
    dbt_valid_from,
    dbt_valid_to
from {{ ref('snap_committee_members') }}
where dbt_valid_to is not null
  and dbt_valid_from >= dbt_valid_to
