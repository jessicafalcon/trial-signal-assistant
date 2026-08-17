#!/usr/bin/env bash
# Cross-target parity proof (SPEC-06 deliverable 3; phase-4 deferral):
# staging row count, the full completeness mart, and the status-change
# transition values (2026-08-17 change-detection ruling) must match
# between duckdb (parquet path) and snowflake (COPY INTO path). Values are
# normalized (dates to YYYY-MM-DD, numerics rounded to 2dp) before
# compare — engines render JSON differently, the arithmetic must not
# differ. Non-zero exit on any mismatch. Runs standalone and as the
# DAG's verify_parity task. Same preflight + pinned non-secret
# connection facts as the other snowflake scripts.
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
PY="${PY:-.venv/bin/python}"

count_query="select count(*) as n from {{ ref('stg_clinical_trials') }}"
mart_query="select * from {{ ref('mart_field_completeness') }} order by ingest_date"
# transition VALUES only — changed_detected_at is each warehouse's own
# snapshot run time and dbt_scd_id hashes it, so neither can ever match
# cross-target. Valid only while both targets snapshot the same days;
# a skipped cloud day that a status change lands on diverges the sets
# legitimately (local-first ruling) — that is a signal, not noise.
# No order by: the compare below sorts every row set itself.
changes_query="select nct_id, prior_status, new_status, prior_source, new_source from {{ ref('mart_trial_status_changes') }}"

tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT

for tgt in duckdb snowflake; do
    "$DBT" --quiet show --inline "$count_query" --output json \
        --project-dir dbt_project --profiles-dir dbt_project \
        --target "$tgt" > "$tmpdir/count_$tgt.json"
    "$DBT" --quiet show --inline "$mart_query" --output json \
        --project-dir dbt_project --profiles-dir dbt_project \
        --target "$tgt" > "$tmpdir/mart_$tgt.json"
    "$DBT" --quiet show --inline "$changes_query" --output json \
        --project-dir dbt_project --profiles-dir dbt_project \
        --target "$tgt" > "$tmpdir/changes_$tgt.json"
done

TMPDIR_PARITY="$tmpdir" "$PY" - <<'EOF'
import json
import os
import sys

tmpdir = os.environ["TMPDIR_PARITY"]


# numeric normalization is scoped to the known measure columns — a
# future string column that happens to look numeric must compare as
# text, not as a rounded float
NUMERIC_COLUMNS = {
    "n",
    "total_studies",
    "pct_with_results",
    "pct_withdrawn_or_terminated_with_why_stopped",
    "pct_date_precision_day",
    "pct_date_precision_month",
    "pct_date_absent",
}


def load(name: str) -> list[dict]:
    with open(os.path.join(tmpdir, name)) as f:
        rows = json.load(f)["show"]
    out = []
    for row in rows:
        norm = {}
        for key, val in row.items():
            key = key.lower()
            if key == "ingest_date":
                norm[key] = str(val)[:10]
            elif key in NUMERIC_COLUMNS and val is not None:
                norm[key] = round(float(val), 2)
            else:
                norm[key] = val
        out.append(norm)
    # whole-row sort key: deterministic for every dataset compared
    # here, including the keyless transition rows
    return sorted(out, key=lambda r: json.dumps(r, sort_keys=True))


failed = False
for label, name in [
    ("staging row count", "count"),
    ("completeness mart", "mart"),
    ("status-change transitions", "changes"),
]:
    duck = load(f"{name}_duckdb.json")
    snow = load(f"{name}_snowflake.json")
    if duck == snow:
        print(f"PARITY OK: {label}: {json.dumps(duck)}")
    else:
        failed = True
        print(f"PARITY MISMATCH: {label}")
        print(f"  duckdb:    {json.dumps(duck)}")
        print(f"  snowflake: {json.dumps(snow)}")

if failed:
    print(
        "hint: snowflake missing one or more partitions (e.g. after a "
        "no-credentials day skipped the load)? Recovery: "
        "make load-snowflake ALL=1. Transitions mismatch: did a status "
        "change land on a day the cloud snapshot skipped? See the "
        "DECISIONS.md change-detection-on-snowflake entry."
    )
sys.exit(1 if failed else 0)
EOF
