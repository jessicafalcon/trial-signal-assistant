#!/usr/bin/env bash
# RAW.TRIALS schema migration (F11): drop + recreate from the current
# DDL via `dbt run-operation recreate_raw_trials`, then re-load with
# make load-snowflake. Destructive by design — the table's contents are
# reproducible from data/parsed (see macros/recreate_raw_trials.sql for
# the full sequence). Same preflight + pinned non-secret connection
# facts as scripts/load_snowflake.sh.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

# destructive-drop gate (review ruling S4; token renamed per the
# 2026-08-17 per-gate-confirm ruling — a shared CONFIRM must not arm
# unrelated destructive gates)
if [ "${CONFIRM_RAW_RECREATE:-}" != "1" ]; then
    echo "ERROR: this drops trial_signal.raw.trials (contents are reproducible from data/parsed)." >&2
    echo "Re-run with CONFIRM_RAW_RECREATE=1 to proceed: CONFIRM_RAW_RECREATE=1 scripts/recreate_raw_trials.sh" >&2
    exit 1
fi

if [ -z "${SNOWFLAKE_ACCOUNT:-}" ] || [ -z "${SNOWFLAKE_USER:-}" ] || [ -z "${SNOWFLAKE_PASSWORD:-}" ]; then
    echo "ERROR: SNOWFLAKE_ACCOUNT / SNOWFLAKE_USER / SNOWFLAKE_PASSWORD not set. Load them first: set -a; source .env; set +a" >&2
    exit 1
fi

export SNOWFLAKE_ROLE=TRANSFORMER
export SNOWFLAKE_WAREHOUSE=TRIAL_SIGNAL_WH
export SNOWFLAKE_DATABASE=TRIAL_SIGNAL
export SNOWFLAKE_SCHEMA=ANALYTICS

DBT="${DBT:-.venv/bin/dbt}"

"$DBT" run-operation recreate_raw_trials \
    --project-dir dbt_project --profiles-dir dbt_project --target snowflake
