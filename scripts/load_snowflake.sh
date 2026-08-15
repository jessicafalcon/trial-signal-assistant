#!/usr/bin/env bash
# COPY INTO RAW.TRIALS via `dbt run-operation` — reuses profiles.yml's
# env_var() credential wiring, so no extra Snowflake client dependency
# and no credential ever appears in a file or in output.
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

"$DBT" run-operation load_raw_trials \
    --project-dir dbt_project --profiles-dir dbt_project --target snowflake
