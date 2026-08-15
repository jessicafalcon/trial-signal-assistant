-- Circuit breaker (R1, SPEC-06): with hard_deletes enabled on the
-- snapshot, a collapsed ingest (truncated pagination, partial API
-- response) would read as mass delisting and close thousands of SCD2
-- rows. Fail the run if the latest partition holds fewer than
-- var('circuit_breaker_min_ratio') of the prior partition's rows.
-- The DAG runs this as its own task before the snapshot; make snapshot
-- runs it too (via make circuit-breaker, whose dbt build creates the
-- staging view this test reads — a bare dbt test on a clean database
-- errors on the missing view). A single-partition store passes: there
-- is no prior partition to compare against.
with partition_counts as (

    select
        ingest_date,
        count(*) as n_trials
    from {{ ref('stg_clinical_trials') }}
    group by ingest_date

),

with_prior as (

    select
        ingest_date,
        n_trials,
        lag(n_trials) over (order by ingest_date) as prior_n_trials
    from partition_counts

)

select
    with_prior.ingest_date,
    with_prior.n_trials,
    with_prior.prior_n_trials
from with_prior
where
    with_prior.ingest_date = (
        select max(partition_counts.ingest_date) from partition_counts
    )
    and with_prior.prior_n_trials is not null
    and with_prior.n_trials
    < {{ var('circuit_breaker_min_ratio') }} * with_prior.prior_n_trials
