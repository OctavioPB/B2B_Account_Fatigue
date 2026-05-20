{% snapshot snap_committee_members %}

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
                'SCD Type 2 history of all CommitteeMember records. '
                'Tracks role changes, title changes, seniority re-classification, '
                'and company transfers. '
                'dbt_valid_to=NULL means the row is the current version. '
                'NEVER UPDATE OR DELETE rows in this table (ADR 0002, CLAUDE.md Hard Rule #3).'
            )
        }
    )
}}

/*
    Source: harmoni_identity.committee_members.

    Key change scenarios captured:
      - Executive promotion (title / seniority_level change → new snapshot row)
      - Role re-weighting (role_weight change → new row)
      - Deactivation (is_active flips FALSE → new row with dbt_valid_to set on previous)
      - CRM ID update (crm_contact_id change → new row)

    Use dbt_valid_to IS NULL to get the current committee composition.
    Use dbt_valid_from <= :ts AND (dbt_valid_to > :ts OR dbt_valid_to IS NULL)
    for point-in-time queries.
*/

select
    id,
    account_id,
    email,
    first_name,
    last_name,
    title,
    department,
    seniority_level,
    role_weight,
    crm_contact_id,
    crm_source,
    is_active,
    last_signal_at,
    created_at,
    updated_at

from {{ source('harmoni_identity', 'committee_members') }}

{% endsnapshot %}
