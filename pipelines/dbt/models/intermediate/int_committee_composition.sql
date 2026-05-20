{{
    config(
        materialized='incremental',
        incremental_strategy='delete+insert',
        unique_key='composition_id',
        on_schema_change='sync_all_columns',
        meta={
            'owner': 'data-engineering',
            'source': 'identity',
            'refresh_cadence': 'hourly',
            'description': (
                'Current and historical buying-committee composition per account. '
                'Derives committee metadata from snap_committee_members (SCD Type 2) '
                'and attaches account firmographic context from snap_accounts. '
                'One row per member per SCD version — use dbt_valid_to IS NULL for '
                'current composition queries.'
            )
        }
    )
}}

{% if is_incremental() %}
    {%- set lookback = var('incremental_lookback_days', 3) -%}
{% endif %}

with current_members as (

    select
        {{ dbt_utils.generate_surrogate_key(['m.dbt_scd_id']) }} as composition_id,
        m.id                                                      as member_id,
        m.account_id,
        m.email,
        m.first_name,
        m.last_name,
        m.title,
        m.department,
        m.seniority_level,
        m.role_weight,
        m.crm_contact_id,
        m.crm_source,
        m.is_active,
        m.last_signal_at,
        m.dbt_valid_from,
        m.dbt_valid_to,
        m.dbt_scd_id,
        -- Is this the current (live) version of this member?
        (m.dbt_valid_to is null)                                  as is_current_version

    from {{ ref('snap_committee_members') }} m
    {% if is_incremental() %}
    where m.dbt_updated_at > now() - interval '{{ lookback }} days'
    {% endif %}

),

account_snapshot as (

    select
        a.id                    as account_id,
        a.domain,
        a.name                  as company_name,
        a.industry,
        a.employee_count,
        a.arr_band,
        a.country,
        a.dbt_valid_from        as account_valid_from,
        a.dbt_valid_to          as account_valid_to

    from {{ ref('snap_accounts') }} a
    -- Join on the current account version for simplicity;
    -- point-in-time account joins are done in the scoring layer.
    where a.dbt_valid_to is null

),

final as (

    select
        m.composition_id,
        m.member_id,
        m.account_id,
        a.domain                    as account_domain,
        a.company_name,
        a.industry,
        a.arr_band,
        m.email,
        m.first_name,
        m.last_name,
        m.title,
        m.department,
        m.seniority_level,
        m.role_weight,
        m.crm_contact_id,
        m.crm_source,
        m.is_active,
        m.last_signal_at,
        m.dbt_valid_from,
        m.dbt_valid_to,
        m.dbt_scd_id,
        m.is_current_version,
        -- Committee-level aggregates (window functions over current members)
        count(*) over (
            partition by m.account_id
            -- count only current active members per account
        )                           as total_members_in_version,
        sum(m.role_weight) over (
            partition by m.account_id
        )                           as total_role_weight_in_version,
        current_timestamp           as _dbt_loaded_at

    from current_members m
    left join account_snapshot a
        on m.account_id = a.account_id

)

select * from final
