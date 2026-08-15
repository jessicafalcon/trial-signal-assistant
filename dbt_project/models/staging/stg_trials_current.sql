-- Latest partition only (grain ruling, DECISIONS.md 2026-08-14): input
-- surface for the snapshot and for mart_trial_documents (RAG). Bare
-- nct_id is unique here.
select
    nct_id,
    brief_title,
    overall_status,
    phase,
    sponsor_name,
    conditions,
    interventions,
    start_date_raw,
    start_date,
    date_precision,
    why_stopped,
    brief_summary,
    detailed_description,
    has_results,
    ingest_date,
    cast('live' as varchar) as snapshot_source
from {{ ref('stg_clinical_trials') }}
where ingest_date = (
    select max(latest.ingest_date)
    from {{ ref('stg_clinical_trials') }} as latest
)
