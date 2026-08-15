-- Grain of stg_clinical_trials is (nct_id, ingest_date) — see the
-- 2026-08-14 grain ruling in DECISIONS.md. Singular test: any row
-- returned here is a duplicate at that grain and fails the test.
select
    nct_id,
    ingest_date,
    count(*) as n_rows
from {{ ref('stg_clinical_trials') }}
group by
    nct_id,
    ingest_date
having count(*) > 1
