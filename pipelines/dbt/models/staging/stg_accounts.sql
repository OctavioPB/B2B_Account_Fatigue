{{
    config(
        materialized='view',
        meta={
            'owner': 'data-engineering',
            'source': 'identity',
            'refresh_cadence': 'realtime',
            'description': 'Cleaned account records from the identity resolution engine.'
        }
    )
}}

with source as (

    select * from {{ source('harmoni_identity', 'accounts') }}

),

renamed as (

    select
        id                                              as account_id,
        lower(trim(domain))                             as domain,
        name                                            as company_name,
        industry,
        employee_count,
        arr_band,
        upper(trim(country))                            as country_code,
        firmographic_source,
        firmographic_enriched_at,
        coalesce(raw_firmographic, '{}'::jsonb)         as raw_firmographic,
        created_at,
        updated_at,

        -- derived: firmographic data is present and recent (< 90 days)
        (
            firmographic_enriched_at is not null
            and firmographic_enriched_at > now() - interval '90 days'
        )                                               as has_fresh_firmographic

    from source

)

select * from renamed
