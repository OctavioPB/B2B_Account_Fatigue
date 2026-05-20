{{
    config(
        materialized='incremental',
        incremental_strategy='delete+insert',
        unique_key=['member_id', 'signal_day', 'source_system'],
        on_schema_change='sync_all_columns',
        meta={
            'owner': 'data-engineering',
            'source': 'all_channels',
            'refresh_cadence': 'hourly',
            'description': (
                'Daily per-member engagement rates rolled up to the account level. '
                'Feeds the Intent Network Model (Sprint 5) for role-weighted signal '
                'aggregation. One row per member per day per channel.'
            )
        }
    )
}}

{% if is_incremental() %}
    {%- set lookback = var('incremental_lookback_days', 3) -%}
{% endif %}

with signals as (

    select
        s.signal_id,
        s.account_domain,
        s.account_id,
        s.contact_email,
        s.source_system,
        s.signal_strength,
        s.signal_strength_score,
        s.is_high_intent,
        s.is_negative,
        date_trunc('day', s.occurred_at)    as signal_day,
        s.occurred_at

    from {{ ref('int_account_signals') }} s
    where s.contact_email is not null
      and s.account_domain is not null
    {% if is_incremental() %}
      and s.occurred_at > now() - interval '{{ lookback }} days'
    {% endif %}

),

-- Join signals to current committee member records
-- Use current snapshot version (dbt_valid_to IS NULL)
members as (

    select
        m.member_id,
        m.account_id,
        m.email,
        m.seniority_level,
        m.role_weight,
        m.is_active

    from {{ ref('int_committee_composition') }} m
    where m.is_current_version = true

),

joined as (

    select
        s.signal_id,
        s.account_domain,
        s.account_id,
        m.member_id,
        s.contact_email,
        m.seniority_level,
        m.role_weight,
        m.is_active,
        s.source_system,
        s.signal_strength,
        s.signal_strength_score,
        s.is_high_intent,
        s.is_negative,
        s.signal_day

    from signals s
    inner join members m
        on  s.contact_email  = m.email
        and s.account_id     = m.account_id

),

aggregated as (

    select
        member_id,
        account_id,
        account_domain,
        source_system,
        signal_day,

        -- Engagement volume
        count(*)                                                as signal_count,

        -- Role-weighted engagement (key input for IntentNetworkModel)
        sum(signal_strength_score * role_weight)                as weighted_signal_score,
        sum(signal_strength_score)                              as raw_signal_score,

        -- Strength breakdown
        count(*) filter (where signal_strength = 'STRONG')      as strong_count,
        count(*) filter (where signal_strength = 'MEDIUM')      as medium_count,
        count(*) filter (where is_high_intent = true)           as high_intent_count,
        count(*) filter (where is_negative = true)              as negative_count,

        -- Member metadata (stable within a day)
        max(seniority_level::text)                              as seniority_level,
        max(role_weight)                                        as role_weight,

        current_timestamp                                       as _refreshed_at

    from joined
    group by 1, 2, 3, 4, 5

)

select * from aggregated
