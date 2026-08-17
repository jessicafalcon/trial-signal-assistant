-- Re-baseline support (change-detection entry, DECISIONS.md
-- 2026-08-17): drops the warehouse snapshot so the day-0 + live
-- sequence can replay from a clean state. Called only by
-- scripts/rebaseline_snowflake_snapshot.sh (CONFIRM=1 gated there).
-- Identifiers hardcoded like recreate_raw_trials (injection ruling).
-- snowflake-only: the duckdb snapshot re-baselines via make reset.
{% macro drop_snapshot_table() %}

    {{ snowflake_only_guard('drop_snapshot_table') }}

    {% do run_query('drop table if exists trial_signal.analytics.snap_trial_status') %}
    {% do log('dropped trial_signal.analytics.snap_trial_status (if it existed)', info=true) %}

{% endmacro %}
