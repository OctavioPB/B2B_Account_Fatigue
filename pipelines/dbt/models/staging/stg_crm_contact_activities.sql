{{
    config(
        materialized='view',
        meta={
            'owner': 'data-engineering',
            'source': 'crm',
            'refresh_cadence': 'realtime',
            'description': 'Cleaned CRM contact activity events from HubSpot, Salesforce, and Pipedrive.'
        }
    )
}}

with source as (

    select * from {{ source('harmoni_raw', 'raw_crm_contact_activities') }}

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
        'CRM'::text                                     as source_system,
        event_type,
        activity_type,
        coalesce(signal_strength, 'WEAK')               as signal_strength,

        -- CRM identifiers
        upper(trim(crm_source))                         as crm_source,
        crm_contact_id,
        crm_company_id,

        -- timestamps
        occurred_at,
        ingested_at,
        _loaded_at,

        -- derived: is this a deal-progression signal?
        (activity_type in (
            'DEAL_STAGE_CHANGED',
            'MEETING_COMPLETED',
            'DEMO_COMPLETED',
            'PROPOSAL_SENT',
            'CONTRACT_SENT'
        ))                                              as is_deal_progression,

        -- derived: is this a high-intent buying signal?
        (activity_type in (
            'PRICING_PAGE_VISIT',
            'ROI_CALCULATOR_USED',
            'SECURITY_REVIEW_STARTED',
            'CONTRACT_SENT',
            'LEGAL_REVIEW_STARTED'
        ))                                              as is_high_intent

    from source
    where occurred_at is not null

)

select * from renamed
