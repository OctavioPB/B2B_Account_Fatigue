{{
    config(
        materialized='view',
        meta={
            'owner': 'data-engineering',
            'source': 'email',
            'refresh_cadence': 'realtime',
            'description': 'Cleaned email engagement events; one row per engagement action.'
        }
    )
}}

with source as (

    select * from {{ source('harmoni_raw', 'raw_email_engagements') }}

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
        'EMAIL'::text                                   as source_system,
        event_type,
        engagement_type,
        coalesce(signal_strength, 'WEAK')               as signal_strength,
        coalesce(is_negative, false)                    as is_negative,

        -- campaign context
        campaign_id,
        message_id,

        -- timestamps
        occurred_at,
        ingested_at,
        _loaded_at,

        -- derived: fatigue signal (negative engagement raises fatigue score)
        case
            when engagement_type = 'UNSUBSCRIBED'   then 'UNSUBSCRIBE'
            when engagement_type = 'SPAM_REPORTED'  then 'SPAM_REPORT'
            when engagement_type = 'BOUNCED'        then 'BOUNCE'
            else null
        end                                             as fatigue_signal_type,

        -- derived: positive engagement strength mapping
        case engagement_type
            when 'REPLIED'      then 3
            when 'CLICKED'      then 2
            when 'OPENED'       then 1
            when 'FORWARDED'    then 2
            else 0
        end                                             as engagement_score

    from source
    where occurred_at is not null

)

select * from renamed
