{% snapshot snap_accounts %}

{{
    config(
        target_schema='snapshots',
        unique_key='id',
        strategy='timestamp',
        updated_at='updated_at',
        invalidate_hard_deletes=false,
        meta={
            'owner': 'data-engineering',
            'source': 'identity',
            'refresh_cadence': 'hourly',
            'description': (
                'SCD Type 2 history of all Account records. '
                'Tracks firmographic changes, domain alias updates, and account status. '
                'dbt_valid_to=NULL means the row is the current version. '
                'NEVER UPDATE OR DELETE rows in this table (ADR 0002, CLAUDE.md Hard Rule #3).'
            )
        }
    )
}}

/*
    Source: harmoni_identity.accounts (operational table from Sprint 3 migration).

    Change detection:
      dbt compares the source row's updated_at to the snapshot's dbt_updated_at.
      Any change to updated_at (triggered by the set_updated_at() PG trigger)
      closes the current snapshot row (sets dbt_valid_to) and inserts a new one.

    Columns added by dbt snapshot:
      dbt_scd_id       UUID  — unique per snapshot row
      dbt_updated_at   TIMESTAMPTZ — when dbt last processed this row
      dbt_valid_from   TIMESTAMPTZ — start of this version's validity
      dbt_valid_to     TIMESTAMPTZ — end of validity (NULL = currently active)
*/

select
    id,
    domain,
    name,
    industry,
    employee_count,
    arr_band,
    country,
    firmographic_source,
    firmographic_enriched_at,
    raw_firmographic,
    created_at,
    updated_at

from {{ source('harmoni_identity', 'accounts') }}

{% endsnapshot %}
