{{
    config(
        materialized='view',
        meta={
            'owner': 'data-engineering',
            'source': 'identity',
            'refresh_cadence': 'realtime',
            'description': 'Cleaned committee member records; one row per active stakeholder per account.'
        }
    )
}}

with source as (

    select * from {{ source('harmoni_identity', 'committee_members') }}

),

renamed as (

    select
        id                                              as member_id,
        account_id,
        lower(trim(email))                              as email,
        trim(first_name)                                as first_name,
        trim(last_name)                                 as last_name,
        title,
        department,
        seniority_level,
        role_weight::numeric(3,2)                       as role_weight,
        crm_contact_id,
        upper(trim(crm_source))                         as crm_source,
        is_active,
        last_signal_at,
        created_at,
        updated_at,

        -- derived: full name for display
        trim(coalesce(first_name, '') || ' ' || coalesce(last_name, ''))
                                                        as display_name,

        -- derived: days since last signal (NULL = never signalled)
        extract(
            epoch from (now() - last_signal_at)
        ) / 86400.0                                     as days_since_last_signal,

        -- derived: is a C-suite or VP stakeholder (high buying influence)
        (seniority_level in ('C_SUITE', 'VP'))          as is_senior_stakeholder

    from source

)

select * from renamed
