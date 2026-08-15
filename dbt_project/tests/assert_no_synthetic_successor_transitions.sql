-- The synthetic day-0 seed may only ever be a PRIOR state. Any row here
-- means the seed was snapshotted on top of live data — out-of-order
-- targets (make dbt before make snapshot-day0) or a snapshot-day0
-- re-run — and the demo transitions are no longer trustworthy.
select
    nct_id,
    prior_source,
    new_source
from {{ ref('mart_trial_status_changes') }}
where new_source = 'synthetic_day0'
