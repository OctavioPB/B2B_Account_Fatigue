{{
    config(
        materialized='view',
        meta={
            'owner': 'data-engineering',
            'source': 'webinar',
            'refresh_cadence': 'realtime',
            'description': 'Cleaned webinar attendance events; one row per attendee per webinar.'
        }
    )
}}

with source as (

    select * from {{ source('harmoni_raw', 'raw_webinar_attendances') }}

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
        'WEBINAR'::text                                 as source_system,
        event_type,
        attendance_type,
        coalesce(signal_strength, 'WEAK')               as signal_strength,

        -- webinar context
        webinar_id,
        webinar_title,
        upper(trim(webinar_provider))                   as webinar_provider,
        webinar_topic,

        -- engagement depth
        coalesce(attended_duration_seconds, 0)          as attended_duration_seconds,
        coalesce(questions_asked, 0)                    as questions_asked,
        coalesce(polls_answered, 0)                     as polls_answered,

        -- timestamps
        occurred_at,
        ingested_at,
        _loaded_at,

        -- derived: attended vs. registered-only
        (attendance_type in ('ATTENDED_LIVE', 'WATCHED_RECORDING'))
                                                        as is_attended,

        -- derived: highly engaged (asked question or answered poll)
        (coalesce(questions_asked, 0) > 0
            or coalesce(polls_answered, 0) > 0)         as is_highly_engaged,

        -- derived: completion rate proxy (> 50% of a 60-min session)
        (coalesce(attended_duration_seconds, 0) > 1800) as is_completed_session

    from source
    where occurred_at is not null

)

select * from renamed
