-- One row per detected status transition: consecutive SCD2 versions of
-- the same nct_id paired via lag(). check strategy only writes a new
-- version when overall_status differs, so every pair is a real change.
with versions as (
    select
        nct_id,
        overall_status,
        snapshot_source,
        dbt_valid_from,
        lag(overall_status) over (
            partition by nct_id
            order by dbt_valid_from
        ) as prior_status,
        lag(snapshot_source) over (
            partition by nct_id
            order by dbt_valid_from
        ) as prior_source
    from {{ ref('snap_trial_status') }}
)

select
    nct_id,
    prior_status,
    overall_status as new_status,
    dbt_valid_from as changed_detected_at,
    prior_source,
    snapshot_source as new_source
from versions
where prior_status is not null
