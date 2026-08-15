"""Daily end-to-end pipeline: ingest -> parse -> guards -> cloud load ->
dual dbt builds -> live snapshot -> RAG reindex -> parity proof.

Every task is a BashOperator cd-ing into the repo mount and calling a
make target: make is the tested interface (pytest + CI run it), so the
DAG orchestrates and never reimplements logic. The repo is mounted at
/usr/local/airflow/repo by docker-compose.override.yml (local only).

Idempotency claim: a second trigger on the same day is a no-op end to
end — same-partition parquet overwrite, delete+FORCE reload of the same
Snowflake partition (R2), snapshot adds 0 rows, rag-build embeds 0.

snapshot-day0 (the synthetic day-0 bootstrap) is deliberately NOT here:
it is a one-time manual step; re-running it would corrupt the demo
transitions (DECISIONS.md 2026-08-14).
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from airflow.providers.standard.operators.bash import BashOperator
from airflow.providers.standard.operators.python import ShortCircuitOperator
from airflow.sdk import DAG, TaskGroup

REPO = "/usr/local/airflow/repo"
# the container has no repo venv: make's PY/DBT overrides point at the
# runtime image's interpreters (same pinned versions via requirements)
MAKE = f"cd {REPO} && make"
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
    missing = [key for key in required if not os.environ.get(key)]
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
        # ShortCircuit: returns False -> downstream skipped. With
        # ignore_downstream_trigger_rules=False the skip stops at
        # dbt_duckdb's none_failed rule, so the local path still runs
        # in a no-credentials environment.
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

        dbt_snowflake = BashOperator(
            task_id="dbt_snowflake",
            bash_command=f"{MAKE} dbt-snowflake {OVERRIDES}",
            **NETWORK_RETRY,
        )

        # row count + completeness mart must match across targets;
        # skipped (default all_success rule) whenever the cloud build
        # skipped, runs after rag_build so it is the run's last word
        verify_parity = BashOperator(
            task_id="verify_parity",
            bash_command=f"{MAKE} verify-parity {OVERRIDES}",
            **NETWORK_RETRY,
        )

        check_cloud_creds >> s3_sync >> load_snowflake >> dbt_snowflake

    # canonical local order incl. the live snapshot: make snapshot
    # (staging build + circuit breaker + dbt snapshot), then full build.
    # none_failed: run even when the cloud group was skipped.
    dbt_duckdb = BashOperator(
        task_id="dbt_duckdb",
        bash_command=f"{MAKE} snapshot {OVERRIDES} && {MAKE} dbt {OVERRIDES}",
        trigger_rule="none_failed",
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

    ingest >> parse >> circuit_breaker >> check_cloud_creds
    dbt_snowflake >> dbt_duckdb >> verify_idempotent >> rag_build
    [rag_build, dbt_snowflake] >> verify_parity
