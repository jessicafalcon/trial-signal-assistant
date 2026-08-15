-- Grain: exactly one document per (nct_id, doc_field). Returns the
-- violating pairs; any row fails the test.
select
    nct_id,
    doc_field,
    count(*) as n
from {{ ref('mart_trial_documents') }}
group by
    nct_id,
    doc_field
having count(*) > 1
