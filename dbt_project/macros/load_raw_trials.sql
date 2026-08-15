-- Idempotent per partition (R2, SPEC-06): each load first deletes the
-- target partition's rows, then COPYs that partition's files with
-- FORCE = TRUE. FORCE is required, not optional: after the delete, an
-- unchanged file is still in COPY's 64-day load history, so a re-run
-- without it would delete the rows and then load 0 files — an empty
-- partition. delete + scoped FORCE makes any same-partition re-run
-- (unchanged file or re-parse) land exactly the file's current rows.
-- Cost: an unchanged partition is rewritten on re-load; scope is one
-- partition per call, so other partitions' history is never touched.
-- All identifiers are hardcoded literals (no target.database): profile
-- fields are env-var-derived and must never reach SQL text (SPEC-02).
-- The partition arg DOES reach SQL text, so it is regex-validated to
-- a date literal before use — anything else fails at compile time.
-- Columns are a manual mirror of SCHEMA in ingest/parse_to_parquet.py:
-- strings everywhere the bridge writes strings (staging owns casting),
-- lists as ARRAY, has_results as BOOLEAN. Extending TrialRecord means
-- a manual DDL migration here — create table IF NOT EXISTS never
-- alters the live table; use recreate_raw_trials (drop + create from
-- this DDL, then re-load — see macros/recreate_raw_trials.sql).

{% macro snowflake_only_guard(macro_name) %}
    {% if target.type != 'snowflake' %}
        {{ exceptions.raise_compiler_error(
            macro_name ~ ' is snowflake-only; run with --target snowflake'
        ) }}
    {% endif %}
{% endmacro %}

{% macro create_raw_trials() %}
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
            brief_summary varchar,
            detailed_description varchar,
            has_results boolean,
            ingest_date varchar
        )
    {% endset %}
    {% do run_query(create_sql) %}
{% endmacro %}

{% macro load_raw_trials(partition) %}

    {{ snowflake_only_guard('load_raw_trials') }}

    {# fullmatch, not match: $ would tolerate a trailing newline #}
    {% set p = partition | string %}
    {% if not modules.re.fullmatch('\\d{4}-\\d{2}-\\d{2}', p) %}
        {{ exceptions.raise_compiler_error(
            'partition must be YYYY-MM-DD, got: ' ~ p
        ) }}
    {% endif %}

    {{ create_raw_trials() }}

    {% set delete_sql %}
        delete from trial_signal.raw.trials
        where ingest_date = '{{ p }}'
    {% endset %}
    {% set deleted = run_query(delete_sql) %}
    {% for row in deleted.rows %}
        {% do log('delete partition ' ~ p ~ ': ' ~ row.values() | join(' | '), info=true) %}
    {% endfor %}

    {% set copy_sql %}
        copy into trial_signal.raw.trials
        from @trial_signal.raw.parsed_trials/ingest_date={{ p }}/
        match_by_column_name = case_insensitive
        force = true
    {% endset %}
    {% set result = run_query(copy_sql) %}
    {% set loaded = namespace(rows=0) %}
    {% for row in result.rows %}
        {% do log(row.values() | join(' | '), info=true) %}
        {% if row['rows_loaded'] is not none %}
            {% set loaded.rows = loaded.rows + row['rows_loaded'] | int %}
        {% endif %}
    {% endfor %}
    {# the delete above already committed — a COPY that finds no files
       returns success with 0 rows and would leave the partition
       silently empty (never-synced partition, bad DATE=). Fail loud. #}
    {% if loaded.rows == 0 %}
        {{ exceptions.raise_compiler_error(
            'COPY loaded 0 rows for partition ' ~ p
            ~ ' — stage path empty? Partition rows were deleted;'
            ~ ' re-run after make s3-sync (or make load-snowflake ALL=1).'
        ) }}
    {% endif %}

{% endmacro %}
