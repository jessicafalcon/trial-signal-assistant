with trials as (

    select
        ingest_date,
        count(*) as total_studies,
        -- sum(case ...) not filter(where ...): snowflake has no FILTER
        -- clause; this form is arithmetic-identical on both targets
        round(
            100.0 * sum(case when has_results then 1 else 0 end)
            / count(*), 2
        ) as pct_with_results,
        round(
            100.0 * sum(case when date_precision = 'day' then 1 else 0 end)
            / count(*), 2
        ) as pct_date_precision_day,
        round(
            100.0 * sum(case when date_precision = 'month' then 1 else 0 end)
            / count(*), 2
        ) as pct_date_precision_month,
        round(
            100.0 * sum(case when start_date_raw is null then 1 else 0 end)
            / count(*), 2
        ) as pct_date_absent
    from {{ ref('stg_clinical_trials') }}
    group by ingest_date

),

stopped as (

    select
        ingest_date,
        round(
            100.0 * count(nullif(why_stopped, '')) / count(*), 2
        ) as pct_withdrawn_or_terminated_with_why_stopped
    from {{ ref('stg_clinical_trials') }}
    where overall_status in ('WITHDRAWN', 'TERMINATED')
    group by ingest_date

)

select
    trials.ingest_date,
    trials.total_studies,
    trials.pct_with_results,
    stopped.pct_withdrawn_or_terminated_with_why_stopped,
    trials.pct_date_precision_day,
    trials.pct_date_precision_month,
    trials.pct_date_absent
from trials
left join stopped on trials.ingest_date = stopped.ingest_date
