{{
    config(
        materialized='view',
        meta={
            'owner': 'data-engineering',
            'source': 'identity',
            'refresh_cadence': 'realtime',
            'description': (
                'Current-state account dimension. View over snap_accounts '
                'filtered to dbt_valid_to IS NULL. '
                'Use this for all "current account profile" queries. '
                'For point-in-time queries, read snap_accounts directly with '
                'a dbt_valid_from/dbt_valid_to predicate.'
            )
        }
    )
}}

with current_accounts as (

    select
        id                                  as account_id,
        domain,
        name                                as company_name,
        industry,
        employee_count,
        arr_band,
        country,
        firmographic_source,
        firmographic_enriched_at,
        raw_firmographic,
        created_at                          as account_created_at,
        updated_at                          as account_updated_at,
        dbt_valid_from                      as scd_valid_from,
        dbt_scd_id,

        -- Derived: firmographic completeness
        (
            name is not null
            and industry is not null
            and employee_count is not null
        )                                   as has_complete_firmographic,

        -- Derived: enrichment freshness
        (
            firmographic_enriched_at is not null
            and firmographic_enriched_at > now() - interval '90 days'
        )                                   as has_fresh_firmographic,

        -- Derived: ARR tier for segmentation
        case arr_band
            when 'STARTUP'          then 1
            when 'SMB'              then 2
            when 'MID_MARKET'       then 3
            when 'ENTERPRISE'       then 4
            when 'LARGE_ENTERPRISE' then 5
            else 0
        end                                 as arr_tier_rank

    from {{ ref('snap_accounts') }}
    where dbt_valid_to is null

)

select * from current_accounts
