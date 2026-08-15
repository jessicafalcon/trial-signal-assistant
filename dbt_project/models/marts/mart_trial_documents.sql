-- The RAG embedder's sole input surface (F8 ruling, DECISIONS.md):
-- one row per (nct_id, doc_field) over the latest partition, long
-- format so each text field embeds as its own document. duckdb-only —
-- excluded on the snowflake target alongside the snapshot machinery
-- (Makefile dbt-snowflake; DECISIONS.md 2026-08-15).
-- content_hash is the incremental change key (F8): the embedder skips
-- ids whose stored hash still matches. conditions_flat joins the array
-- with '; ' because Chroma metadata values must be scalars (F8).
-- Nullable scalars coalesce to '' — Chroma metadata rejects nulls, and
-- '' keeps absent distinguishable from any real value (phase 'NA' is a
-- real registry value, so it can't double as the absent marker).

with current_trials as (

    select
        nct_id,
        overall_status,
        has_results,
        ingest_date,
        brief_summary,
        detailed_description,
        why_stopped,
        coalesce(phase, '') as phase,
        coalesce(sponsor_name, '') as sponsor_name,
        coalesce(array_to_string(conditions, '; '), '') as conditions_flat
    from {{ ref('stg_trials_current') }}

),

docs as (

    select
        nct_id,
        'brief_summary' as doc_field,
        brief_summary as doc_text,
        overall_status,
        phase,
        sponsor_name,
        has_results,
        conditions_flat,
        ingest_date
    from current_trials

    union all

    select
        nct_id,
        'detailed_description' as doc_field,
        detailed_description as doc_text,
        overall_status,
        phase,
        sponsor_name,
        has_results,
        conditions_flat,
        ingest_date
    from current_trials

    union all

    select
        nct_id,
        'why_stopped' as doc_field,
        why_stopped as doc_text,
        overall_status,
        phase,
        sponsor_name,
        has_results,
        conditions_flat,
        ingest_date
    from current_trials

)

-- doc_text is stored trimmed and hashed trimmed, so a whitespace-only
-- registry change never flips content_hash (review ruling C8)
select
    nct_id,
    doc_field,
    overall_status,
    phase,
    sponsor_name,
    has_results,
    conditions_flat,
    ingest_date,
    trim(doc_text) as doc_text,
    md5(trim(doc_text)) as content_hash
from docs
where trim(coalesce(doc_text, '')) != ''
