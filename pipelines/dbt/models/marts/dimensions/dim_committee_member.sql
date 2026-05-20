{{
    config(
        materialized='view',
        meta={
            'owner': 'data-engineering',
            'source': 'identity',
            'refresh_cadence': 'realtime',
            'description': (
                'Current-state committee member dimension. View over '
                'snap_committee_members filtered to dbt_valid_to IS NULL. '
                'Joined with dim_account for account context. '
                'Use for all "who is on the buying committee right now?" queries.'
            )
        }
    )
}}

with current_members as (

    select
        id                                      as member_id,
        account_id,
        email,
        first_name,
        last_name,
        title,
        department,
        seniority_level,
        role_weight,
        crm_contact_id,
        crm_source,
        is_active,
        last_signal_at,
        created_at                              as member_created_at,
        updated_at                              as member_updated_at,
        dbt_valid_from                          as scd_valid_from,
        dbt_scd_id,

        -- Derived: display name
        trim(
            coalesce(first_name, '')
            || ' '
            || coalesce(last_name, '')
        )                                       as display_name,

        -- Derived: days since last engagement
        extract(epoch from (now() - last_signal_at)) / 86400.0
                                                as days_since_last_signal,

        -- Derived: is senior buying-committee stakeholder
        (seniority_level in ('C_SUITE', 'VP')) as is_senior_stakeholder,

        -- Derived: is the member currently silent (no signal in 30d)
        (
            last_signal_at is null
            or last_signal_at < now() - interval '30 days'
        )                                       as is_silent

    from {{ ref('snap_committee_members') }}
    where dbt_valid_to is null

),

with_account as (

    select
        m.*,
        a.domain                                as account_domain,
        a.company_name,
        a.industry,
        a.arr_band,
        a.arr_tier_rank,
        a.country

    from current_members m
    left join {{ ref('dim_account') }} a
        on m.account_id = a.account_id

)

select * from with_account
