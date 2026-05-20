/*
    Singular test: assert_snapshot_has_current_row
    =========================================================================
    Verifies that every entity in both SCD snapshots has exactly one current
    row (dbt_valid_to IS NULL).

    Violations indicate:
    - More than one current row: snapshot ran twice without closing the previous
      (dbt bug or direct INSERT into the snapshots schema).
    - Zero current rows: entity was "hard-deleted" from the source and
      invalidate_hard_deletes is not working as expected.

    Returns non-zero rows on failure.
*/

with account_current_counts as (
    select
        'snap_accounts'     as snapshot_table,
        id                  as entity_id,
        count(*)            as current_row_count
    from {{ ref('snap_accounts') }}
    where dbt_valid_to is null
    group by id
    having count(*) != 1
),

member_current_counts as (
    select
        'snap_committee_members' as snapshot_table,
        id                       as entity_id,
        count(*)                 as current_row_count
    from {{ ref('snap_committee_members') }}
    where dbt_valid_to is null
    group by id
    having count(*) != 1
)

select * from account_current_counts
union all
select * from member_current_counts
