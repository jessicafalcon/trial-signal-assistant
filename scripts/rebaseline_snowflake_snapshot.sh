#!/usr/bin/env bash
# Re-baseline the Snowflake snapshot (change-detection entry,
# DECISIONS.md 2026-08-17): drop ANALYTICS.SNAP_TRIAL_STATUS, then
# replay the one-time day-0 bootstrap and a breaker-guarded live
# snapshot. Recovery path for a diverged or wrongly-baselined
# warehouse SCD2 history (e.g. the DAG snapshotted before the day-0
# bootstrap ever ran). Destructive by design: the replayed history
# holds day-0 + current state only — intermediate live transitions,
# if any, are NOT reconstructable. Same preflight + pinned
# non-secret connection facts as the other snowflake scripts.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

# destructive-drop gate. Per-gate token (DECISIONS.md 2026-08-17
# per-gate-confirm entry): this gate answers ONLY to
# CONFIRM_REBASELINE — a token exported for another destructive
# operation must not arm this one.
if [ "${CONFIRM_REBASELINE:-}" != "1" ]; then
    echo "ERROR: this drops trial_signal.analytics.snap_trial_status and replays day-0 + live." >&2
    echo "Intermediate live history, if any, is NOT reconstructable." >&2
    echo "Re-run with CONFIRM_REBASELINE=1 to proceed: CONFIRM_REBASELINE=1 scripts/rebaseline_snowflake_snapshot.sh" >&2
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

"$DBT" run-operation drop_snapshot_table \
    --project-dir dbt_project --profiles-dir dbt_project --target snowflake

# replay: precondition before re-bootstrapping alongside a live duckdb
# history — verify duckdb's mart holds ONLY day-0 transitions first,
# or transition parity legitimately diverges (DECISIONS.md caveat)
make snapshot-day0-snowflake DBT="$DBT"
make snapshot-snowflake DBT="$DBT"
