{{
    config(
        materialized='view',
        meta={
            'owner': 'data-engineering',
            'source': 'web',
            'refresh_cadence': 'realtime',
            'description': 'Cleaned web pageview events; one row per pageview.'
        }
    )
}}

with source as (

    select * from {{ source('harmoni_raw', 'raw_web_pageviews') }}

),

renamed as (

    select
        -- keys
        id                                              as raw_id,
        event_id,

        -- account attribution
        lower(trim(account_domain))                     as account_domain,
        lower(trim(contact_email))                      as contact_email,

        -- event classification
        'WEB'::text                                     as source_system,
        event_type,
        coalesce(signal_strength, 'WEAK')               as signal_strength,
        coalesce(page_category, 'OTHER')                as page_category,

        -- content
        page_url,
        page_title,
        time_on_page_seconds,
        session_id,

        -- timestamps
        occurred_at,
        ingested_at,
        _loaded_at,

        -- derived: flag high-intent pages
        (page_category in ('PRICING', 'DEMO'))          as is_high_intent_page,

        -- derived: minimum engagement threshold (> 30 seconds)
        (time_on_page_seconds is not null
            and time_on_page_seconds > 30)              as is_engaged_session

    from source
    where occurred_at is not null

)

select * from renamed
