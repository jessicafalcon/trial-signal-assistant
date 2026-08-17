-- Schema migration for RAW.TRIALS (F11): the table is a manual mirror
-- of the bridge SCHEMA and IF NOT EXISTS never alters it, so a
-- TrialRecord extension is applied by dropping and recreating from the
-- current DDL, then re-loading — the data is reproducible by design.
-- Full sequence (also in README "Cloud target"; the script requires
-- CONFIRM_RAW_RECREATE=1 before it will drop):
--   make parse && make s3-sync \
--     && CONFIRM_RAW_RECREATE=1 scripts/recreate_raw_trials.sh \
--     && make load-snowflake ALL=1 && make dbt-snowflake
-- (ALL=1: the fresh table needs every local partition, not just the
-- latest — make load-snowflake is per-partition since R2.)
{% macro recreate_raw_trials() %}

    {{ snowflake_only_guard('recreate_raw_trials') }}

    {% do run_query('drop table if exists trial_signal.raw.trials') %}
    {% do log('dropped trial_signal.raw.trials', info=true) %}
    {{ create_raw_trials() }}
    {% do log('recreated trial_signal.raw.trials from current DDL', info=true) %}

{% endmacro %}
