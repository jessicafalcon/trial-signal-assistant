#!/usr/bin/env bash
# COPY INTO RAW.TRIALS via `dbt run-operation` — reuses profiles.yml's
# env_var() credential wiring, so no extra Snowflake client dependency
# and no credential ever appears in a file or in output.
# Per-partition (R2): each invocation deletes the partition's rows and
# re-COPYs its files with FORCE (see macros/load_raw_trials.sql), so a
# same-partition re-run is safe. Default partition = latest local dir
# in data/parsed/; DATE=YYYY-MM-DD picks one; ALL=1 loads every local
# partition in order (the re-load path after recreate_raw_trials.sh).
# Self-contained entry point: carries the same preflight and pinned
# non-secret connection facts as the Makefile targets, so a direct
# invocation cannot silently run on the caller's .env role/warehouse.
set -euo pipefail

if [ -z "${SNOWFLAKE_ACCOUNT:-}" ] || [ -z "${SNOWFLAKE_USER:-}" ] || [ -z "${SNOWFLAKE_PASSWORD:-}" ]; then
    echo "ERROR: SNOWFLAKE_ACCOUNT / SNOWFLAKE_USER / SNOWFLAKE_PASSWORD not set. Load them first: set -a; source .env; set +a" >&2
    exit 1
fi

export SNOWFLAKE_ROLE=TRANSFORMER
export SNOWFLAKE_WAREHOUSE=TRIAL_SIGNAL_WH
export SNOWFLAKE_DATABASE=TRIAL_SIGNAL
export SNOWFLAKE_SCHEMA=ANALYTICS

DBT="${DBT:-.venv/bin/dbt}"

# `|| true`: under set -e a failing ls would abort the script here and
# the "no partitions" message below would never print (empty-tree case)
if [ -n "${DATE:-}" ]; then
    partitions="$DATE"
elif [ "${ALL:-}" = "1" ]; then
    partitions=$( (ls -d data/parsed/ingest_date=*/ 2>/dev/null || true) | sed 's|.*ingest_date=||; s|/$||' | sort)
else
    partitions=$( (ls -d data/parsed/ingest_date=*/ 2>/dev/null || true) | sed 's|.*ingest_date=||; s|/$||' | sort | tail -1)
fi

if [ -z "$partitions" ]; then
    echo "ERROR: no partitions found in data/parsed/ (run make parse, or pass DATE=YYYY-MM-DD)" >&2
    exit 1
fi

for p in $partitions; do
    # the macro re-validates; this catches bad DATE= input with a
    # clearer error before a dbt invocation
    if ! [[ "$p" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
        echo "ERROR: partition must be YYYY-MM-DD, got: $p" >&2
        exit 1
    fi
    "$DBT" run-operation load_raw_trials --args "{partition: \"$p\"}" \
        --project-dir dbt_project --profiles-dir dbt_project --target snowflake
done
