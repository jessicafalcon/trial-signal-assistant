select
    cast(nct_id as varchar) as nct_id,
    cast(brief_title as varchar) as brief_title,
    cast(overall_status as varchar) as overall_status,
    cast(phase as varchar) as phase,
    cast(sponsor_name as varchar) as sponsor_name,
    -- lists arrive as ARRAY on snowflake (COPY from parquet), as
    -- varchar[] on duckdb — the only cross-target type divergence
    {% if target.type == 'snowflake' %}
        conditions,
        interventions,
    {% else %}
        cast(conditions as varchar[]) as conditions,
        cast(interventions as varchar[]) as interventions,
    {% endif %}
    cast(start_date_raw as varchar) as start_date_raw,
    cast(start_date as date) as start_date,
    cast(date_precision as varchar) as date_precision,
    cast(why_stopped as varchar) as why_stopped,
    cast(has_results as boolean) as has_results,
    cast(ingest_date as date) as ingest_date
from {{ source('parsed', 'clinical_trials') }}
