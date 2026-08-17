-- Operational history of the raw landing: one row per parsed
-- partition with its day-over-day movement. ratio_vs_prior is the
-- same quantity the circuit breaker gates on
-- (circuit_breaker_min_ratio) — kept here, not gated, so drift is
-- visible after the fact and queryable in the warehouse.
with partitions as (

    select
        ingest_date,
        count(*) as rows_ingested,
        count(distinct nct_id) as distinct_studies
    from {{ ref('stg_clinical_trials') }}
    group by ingest_date

),

with_prior as (

    select
        ingest_date,
        rows_ingested,
        distinct_studies,
        lag(rows_ingested) over (order by ingest_date) as prior_rows,
        lag(ingest_date) over (order by ingest_date) as prior_ingest_date
    from partitions

)

select
    ingest_date,
    rows_ingested,
    distinct_studies,
    prior_rows,
    rows_ingested - prior_rows as delta_rows,
    round(1.0 * rows_ingested / prior_rows, 4) as ratio_vs_prior,
    datediff('day', prior_ingest_date, ingest_date) as days_since_prior
from with_prior
