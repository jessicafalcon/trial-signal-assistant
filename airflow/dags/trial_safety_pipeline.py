"""Daily end-to-end pipeline: ingest -> parse -> guards -> local dbt
(live snapshot + build) -> RAG reindex, then cloud load -> snowflake
build -> parity proof.

Local before cloud (post-phase-6 owner ruling, supersedes the SPEC-06
chain): the snapshot's daily timing is the one artifact not fully
recoverable later (same-day manual recovery only), while a missed
cloud load is re-loadable any time (make load-snowflake ALL=1) — so
the recoverable step sits downstream of the unrecoverable one, and a
cloud outage can no longer cost a snapshot day. The two dbt paths stay
serialized regardless: they share dbt_project/'s target/ and logs/.

Every task is a BashOperator cd-ing into the repo mount and calling a
make target: make is the tested interface (pytest + CI run it), so the
DAG orchestrates and never reimplements logic. The repo is mounted at
/usr/local/airflow/repo by docker-compose.override.yml (local only).

Idempotency claim: a second trigger on the same day is a no-op end to
end — same-partition parquet overwrite, delete+FORCE reload of the same
Snowflake partition (R2), snapshot adds 0 rows, rag-build embeds 0.

snapshot-day0 and snapshot-day0-snowflake (the synthetic day-0
bootstraps) are deliberately NOT here: one-time manual steps whose
re-run would corrupt the demo transitions (DECISIONS.md 2026-08-14).
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from airflow.providers.standard.operators.bash import BashOperator
from airflow.providers.standard.operators.python import ShortCircuitOperator
from airflow.sdk import DAG, TaskGroup

REPO = "/usr/local/airflow/repo"
# dbt's target/ artifacts include the partial-parse cache, which stores
# ABSOLUTE file paths. Host and container share the repo mount at
# different absolute paths, so they must not share those dirs: a
# host-side dbt run poisons the cache with /Users/... paths and the
# next in-container seed load fails on them (observed 2026-08-15).
# Container-scoped dirs, both gitignored.
DBT_ENV = (
    f"DBT_TARGET_PATH={REPO}/dbt_project/target_container "
    f"DBT_LOG_PATH={REPO}/dbt_project/logs_container"
)
# the container has no repo venv: make's PY/DBT overrides point at the
# runtime image's interpreters (same pinned versions via requirements)
MAKE = f"cd {REPO} && {DBT_ENV} make"
OVERRIDES = "PY=python DBT=dbt"

# network tasks get retries with exponential backoff and a longer
# timeout; local deterministic tasks get no retries — a failure there
# is a bug, and a retry would only repeat it. Every task carries an
# execution_timeout because max_active_runs=1 means one hung task
# blocks the schedule indefinitely.
NETWORK_RETRY: dict = {
    "retries": 2,
    "retry_delay": timedelta(minutes=1),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=10),
    "execution_timeout": timedelta(minutes=30),
}


def _cloud_creds_present() -> bool:
    """Skip-with-reason gate for the cloud TaskGroup (ShortCircuit)."""
    required = [
        "SNOWFLAKE_ACCOUNT",
        "SNOWFLAKE_USER",
        "SNOWFLAKE_PASSWORD",
        "AWS_PROFILE",
    ]
    # .strip(): a whitespace-only value is "missing" — without it the
    # gate passed and the run failed later at Snowflake auth, after
    # retries (phase-6 documented residual, fixed on phase-7 ruling)
    missing = [key for key in required if not os.environ.get(key, "").strip()]
    if missing:
        # lands in the task log as the skip reason; values never logged
        print(f"cloud tasks skipped: missing env {', '.join(missing)}")
        return False
    return True


with DAG(
    dag_id="trial_safety_pipeline",
    description="AD trial ingest -> dual dbt -> snapshot -> RAG, daily",
    schedule="@daily",
    start_date=datetime(2026, 8, 15, tzinfo=timezone.utc),
    catchup=False,  # ingest fetches "today" — backfills are meaningless
    max_active_runs=1,  # tasks share one duckdb file and one partition
    default_args={
        "retries": 0,
        "execution_timeout": timedelta(minutes=15),
    },
    tags=["trial-signal"],
) as dag:
    ingest = BashOperator(
        task_id="ingest",
        bash_command=f"{MAKE} ingest {OVERRIDES}",
        **NETWORK_RETRY,
    )

    parse = BashOperator(
        task_id="parse",
        bash_command=f"{MAKE} parse {OVERRIDES}",
    )

    # R1 guard: never snapshot (or ship) a collapsed ingest — fails if
    # the latest partition < circuit_breaker_min_ratio of the prior one
    circuit_breaker = BashOperator(
        task_id="circuit_breaker",
        bash_command=f"{MAKE} circuit-breaker {OVERRIDES}",
    )

    with TaskGroup(group_id="cloud") as cloud:
        # ShortCircuit: returns False -> downstream skipped. Everything
        # downstream of this gate is cloud-only (the local path already
        # finished upstream); ignore_downstream_trigger_rules=False
        # lets the skip flow through trigger rules, so verify_parity
        # inherits it via its default all_success rule.
        check_cloud_creds = ShortCircuitOperator(
            task_id="check_cloud_creds",
            python_callable=_cloud_creds_present,
            ignore_downstream_trigger_rules=False,
        )

        s3_sync = BashOperator(
            task_id="s3_sync",
            bash_command=f"{MAKE} s3-sync {OVERRIDES}",
            **NETWORK_RETRY,
        )

        # R2 path: delete-by-partition + scoped COPY FORCE — the
        # same-day re-run converges instead of appending duplicates
        load_snowflake = BashOperator(
            task_id="load_snowflake",
            bash_command=f"{MAKE} load-snowflake {OVERRIDES}",
            **NETWORK_RETRY,
        )

        # mirrors dbt_duckdb: breaker-guarded snapshot on the warehouse
        # copy, then the full build (change detection runs on both
        # targets — external-review ruling). Runs after load_snowflake,
        # so a thin partition here means a collapsed ingest shipped,
        # not "not loaded yet". A retry re-snapshots the same data: 0
        # new rows, idempotent.
        dbt_snowflake = BashOperator(
            task_id="dbt_snowflake",
            bash_command=(
                f"{MAKE} snapshot-snowflake {OVERRIDES}"
                f" && {MAKE} dbt-snowflake {OVERRIDES}"
            ),
            **NETWORK_RETRY,
        )

        # row count, completeness mart, and status-change transition
        # values must match across targets; skipped (default
        # all_success rule) whenever the cloud build skipped, runs
        # after rag_build so it is the run's last word
        verify_parity = BashOperator(
            task_id="verify_parity",
            bash_command=f"{MAKE} verify-parity {OVERRIDES}",
            **NETWORK_RETRY,
        )

        check_cloud_creds >> s3_sync >> load_snowflake >> dbt_snowflake

    # canonical local order incl. the live snapshot: make snapshot
    # (staging build + circuit breaker + dbt snapshot), then full build.
    # Runs BEFORE the cloud group — nothing upstream can skip or fail
    # for cloud reasons, so the default trigger rule applies.
    dbt_duckdb = BashOperator(
        task_id="dbt_duckdb",
        bash_command=f"{MAKE} snapshot {OVERRIDES} && {MAKE} dbt {OVERRIDES}",
    )

    verify_idempotent = BashOperator(
        task_id="verify_idempotent",
        bash_command=f"{MAKE} verify-idempotent {OVERRIDES}",
    )

    # incremental by content_hash: an unchanged mart embeds 0 documents.
    # network: first run in a fresh container downloads the pinned model
    rag_build = BashOperator(
        task_id="rag_build",
        bash_command=f"{MAKE} rag-build {OVERRIDES}",
        **NETWORK_RETRY,
    )

    ingest >> parse >> circuit_breaker >> dbt_duckdb
    dbt_duckdb >> verify_idempotent >> rag_build
    verify_idempotent >> check_cloud_creds
    [rag_build, dbt_snowflake] >> verify_parity
