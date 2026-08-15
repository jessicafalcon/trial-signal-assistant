-- Idempotent for byte-identical files: COPY INTO keeps per-table load
-- history (64 days), so an unchanged staged file is skipped and a
-- re-run loads 0 rows. A re-parse rewrites the parquet (new content
-- hash) and IS re-loaded into this append-only table — the staging
-- grain test is the loud failure; reset mechanics are deferred to
-- Phase 6 with invalidate_hard_deletes (DECISIONS.md 2026-08-15).
-- All identifiers are hardcoded literals (no target.database): profile
-- fields are env-var-derived and must never reach SQL text (SPEC-02).
-- Columns are a manual mirror of SCHEMA in ingest/parse_to_parquet.py:
-- strings everywhere the bridge writes strings (staging owns casting),
-- lists as ARRAY, has_results as BOOLEAN. Extending TrialRecord means
-- a manual DDL migration here — create table IF NOT EXISTS never
-- alters the live table.
{% macro load_raw_trials() %}

    {% if target.type != 'snowflake' %}
        {{ exceptions.raise_compiler_error(
            'load_raw_trials is snowflake-only; run with --target snowflake'
        ) }}
    {% endif %}

    {% set create_sql %}
        create table if not exists trial_signal.raw.trials (
            nct_id varchar,
            brief_title varchar,
            overall_status varchar,
            phase varchar,
            sponsor_name varchar,
            conditions array,
            interventions array,
            start_date_raw varchar,
            start_date varchar,
            date_precision varchar,
            why_stopped varchar,
            has_results boolean,
            ingest_date varchar
        )
    {% endset %}
    {% do run_query(create_sql) %}

    {% set copy_sql %}
        copy into trial_signal.raw.trials
        from @trial_signal.raw.parsed_trials
        match_by_column_name = case_insensitive
    {% endset %}
    {% set result = run_query(copy_sql) %}
    {% for row in result.rows %}
        {% do log(row.values() | join(' | '), info=true) %}
    {% endfor %}

{% endmacro %}
