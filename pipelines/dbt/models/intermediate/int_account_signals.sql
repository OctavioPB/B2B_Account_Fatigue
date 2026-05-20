{{
    config(
        materialized='incremental',
        incremental_strategy='delete+insert',
        unique_key='signal_id',
        on_schema_change='sync_all_columns',
        meta={
            'owner': 'data-engineering',
            'source': 'all_channels',
            'refresh_cadence': 'hourly',
            'description': (
                'Unified signal stream across all four source channels (web, email, CRM, webinar). '
                'One row per intent signal, attributed to an Account via account_domain. '
                'Joins back to stg_accounts to attach account_id for downstream scoring. '
                'Incremental: processes only signals ingested since the last run.'
            )
        }
    )
}}

/*
    Incremental filter: on non-full-refresh runs, only process rows
    that arrived after the last watermark. Uses ingested_at (not occurred_at)
    to avoid re-processing delays caused by late-arriving events.
    lookback window prevents gaps at watermark boundaries.
*/
{% if is_incremental() %}
    {%- set lookback = var('incremental_lookback_days', 3) -%}
    {%- set max_loaded = "select coalesce(max(ingested_at), '1970-01-01'::timestamptz) from " ~ this -%}
{% endif %}

with web as (

    select
        {{ dbt_utils.generate_surrogate_key(['raw_id', "'WEB'"]) }}  as signal_id,
        event_id,
        account_domain,
        contact_email,
        'WEB'                                                         as source_system,
        event_type,
        signal_strength,
        occurred_at,
        ingested_at,
        -- channel-specific payload (JSON serialised for unified schema)
        jsonb_build_object(
            'page_category',    page_category,
            'page_url',         page_url,
            'is_high_intent',   is_high_intent_page,
            'is_engaged',       is_engaged_session
        )                                                             as signal_payload,
        is_high_intent_page                                           as is_high_intent,
        false                                                         as is_negative

    from {{ ref('stg_web_pageviews') }}
    {% if is_incremental() %}
    where ingested_at > ({{ max_loaded }}) - interval '{{ lookback }} days'
    {% endif %}

),

email as (

    select
        {{ dbt_utils.generate_surrogate_key(['raw_id', "'EMAIL'"]) }} as signal_id,
        event_id,
        account_domain,
        contact_email,
        'EMAIL'                                                        as source_system,
        event_type,
        signal_strength,
        occurred_at,
        ingested_at,
        jsonb_build_object(
            'engagement_type',  engagement_type,
            'campaign_id',      campaign_id,
            'engagement_score', engagement_score,
            'fatigue_signal',   fatigue_signal_type
        )                                                              as signal_payload,
        false                                                          as is_high_intent,
        is_negative

    from {{ ref('stg_email_engagements') }}
    {% if is_incremental() %}
    where ingested_at > ({{ max_loaded }}) - interval '{{ lookback }} days'
    {% endif %}

),

crm as (

    select
        {{ dbt_utils.generate_surrogate_key(['raw_id', "'CRM'"]) }}   as signal_id,
        event_id,
        account_domain,
        contact_email,
        'CRM'                                                          as source_system,
        event_type,
        signal_strength,
        occurred_at,
        ingested_at,
        jsonb_build_object(
            'activity_type',        activity_type,
            'crm_source',           crm_source,
            'is_deal_progression',  is_deal_progression,
            'is_high_intent',       is_high_intent
        )                                                              as signal_payload,
        is_high_intent                                                 as is_high_intent,
        false                                                          as is_negative

    from {{ ref('stg_crm_contact_activities') }}
    {% if is_incremental() %}
    where ingested_at > ({{ max_loaded }}) - interval '{{ lookback }} days'
    {% endif %}

),

webinar as (

    select
        {{ dbt_utils.generate_surrogate_key(['raw_id', "'WEBINAR'"]) }} as signal_id,
        event_id,
        account_domain,
        contact_email,
        'WEBINAR'                                                         as source_system,
        event_type,
        signal_strength,
        occurred_at,
        ingested_at,
        jsonb_build_object(
            'attendance_type',   attendance_type,
            'webinar_topic',     webinar_topic,
            'is_attended',       is_attended,
            'is_highly_engaged', is_highly_engaged
        )                                                                 as signal_payload,
        is_attended                                                       as is_high_intent,
        false                                                             as is_negative

    from {{ ref('stg_webinar_attendances') }}
    {% if is_incremental() %}
    where ingested_at > ({{ max_loaded }}) - interval '{{ lookback }} days'
    {% endif %}

),

all_signals as (
    select * from web
    union all
    select * from email
    union all
    select * from crm
    union all
    select * from webinar
),

-- Attach account_id by joining on domain; signals without a resolved account
-- are kept (account_id=NULL) so that ops can backfill after quarantine resolution.
enriched as (

    select
        s.signal_id,
        s.event_id,
        s.account_domain,
        a.account_id,
        s.contact_email,
        s.source_system,
        s.event_type,
        s.signal_strength,
        s.occurred_at,
        s.ingested_at,
        s.signal_payload,
        s.is_high_intent,
        s.is_negative,
        -- Numeric strength for scoring (WEAK=1, MEDIUM=2, STRONG=3)
        case s.signal_strength
            when 'STRONG' then 3
            when 'MEDIUM' then 2
            else 1
        end                                 as signal_strength_score,
        current_timestamp                   as _dbt_loaded_at

    from all_signals s
    left join {{ ref('stg_accounts') }} a
        on s.account_domain = a.domain

)

select * from enriched
