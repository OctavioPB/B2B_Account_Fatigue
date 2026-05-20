{{
    config(
        materialized='incremental',
        incremental_strategy='delete+insert',
        unique_key=['account_domain', 'signal_hour', 'source_system'],
        on_schema_change='sync_all_columns',
        meta={
            'owner': 'data-engineering',
            'source': 'all_channels',
            'refresh_cadence': 'hourly',
            'description': (
                'Hourly aggregated signal counts per account per channel. '
                'Primary input for the Account Fatigue Score engine (Sprint 6) '
                'and Intent Network Model (Sprint 5). '
                'Written to ClickHouse when run with --target clickhouse.'
            )
        }
    )
}}

{% if is_incremental() %}
    {%- set lookback = var('incremental_lookback_days', 3) -%}
{% endif %}

with signals as (

    select
        account_domain,
        account_id,
        source_system,
        date_trunc('hour', occurred_at)                     as signal_hour,
        signal_strength,
        signal_strength_score,
        is_high_intent,
        is_negative,
        contact_email

    from {{ ref('int_account_signals') }}
    where account_domain is not null
    {% if is_incremental() %}
      and occurred_at > now() - interval '{{ lookback }} days'
    {% endif %}

),

aggregated as (

    select
        account_domain,
        -- Take the most recent account_id (may change if domain was re-resolved)
        max(account_id)                                     as account_id,
        source_system,
        signal_hour,

        -- Volume
        count(*)                                            as signal_count,
        count(distinct contact_email)                       as unique_member_count,

        -- Strength breakdown
        count(*) filter (where signal_strength = 'STRONG')  as strong_signal_count,
        count(*) filter (where signal_strength = 'MEDIUM')  as medium_signal_count,
        count(*) filter (where signal_strength = 'WEAK')    as weak_signal_count,

        -- Weighted signal score (used by scoring engine)
        sum(signal_strength_score)                          as total_strength_score,
        avg(signal_strength_score)                          as avg_strength_score,

        -- Intent and fatigue
        count(*) filter (where is_high_intent = true)       as high_intent_signal_count,
        count(*) filter (where is_negative = true)          as negative_signal_count,

        current_timestamp                                   as _refreshed_at

    from signals
    group by 1, 3, 4

)

select * from aggregated
