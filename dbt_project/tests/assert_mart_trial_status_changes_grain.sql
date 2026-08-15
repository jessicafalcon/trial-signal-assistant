-- Grain of mart_trial_status_changes is (nct_id, changed_detected_at):
-- one transition per trial per snapshot run. Any row returned is a
-- duplicate at that grain.
select
    nct_id,
    changed_detected_at,
    count(*) as n_rows
from {{ ref('mart_trial_status_changes') }}
group by
    nct_id,
    changed_detected_at
having count(*) > 1
