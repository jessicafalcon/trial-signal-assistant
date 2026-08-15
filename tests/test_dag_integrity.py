"""DAG integrity tests — no Docker, no Airflow runtime, no credentials.

airflow is a test-only dependency isolated in
airflow/requirements-dagtest.txt (installed by make dag-verify, never
by make setup). Without it these tests SKIP so make test stays green
on a fresh venv; make dag-verify sets DAG_TESTS_REQUIRED=1 so a broken
install fails loudly instead of skipping.
"""

from __future__ import annotations

import os
import re
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# airflow creates AIRFLOW_HOME (cfg + logs) on first import — keep that
# out of the user's home and CI workspace. Must be set before import.
os.environ.setdefault("AIRFLOW_HOME", tempfile.mkdtemp(prefix="airflow-home-"))
os.environ.setdefault("AIRFLOW__CORE__LOAD_EXAMPLES", "False")

# probe airflow.models, not airflow: the repo's airflow/ (Astro
# project) is a namespace package that makes bare `import airflow`
# succeed vacuously; an installed apache-airflow (regular package)
# still wins the import per PEP 420
if os.environ.get("DAG_TESTS_REQUIRED") == "1":
    import airflow.models  # noqa: F401  — fail loudly, never skip
else:
    pytest.importorskip(
        "airflow.models", reason="airflow not installed; run make dag-verify"
    )

from airflow.models import DagBag
from airflow.providers.standard.operators.bash import BashOperator
from airflow.providers.standard.operators.python import (
    ShortCircuitOperator,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DAG_FOLDER = str(REPO_ROOT / "airflow" / "dags")
DAG_ID = "trial_safety_pipeline"

# the documented order: local chain first, then cloud (post-phase-6
# owner ruling — supersedes the SPEC-06 deliverable-2 chain; see the
# DECISIONS.md local-first entry). task_id -> upstream ids
EXPECTED_UPSTREAMS: dict[str, set[str]] = {
    "ingest": set(),
    "parse": {"ingest"},
    "circuit_breaker": {"parse"},
    "dbt_duckdb": {"circuit_breaker"},
    "verify_idempotent": {"dbt_duckdb"},
    "rag_build": {"verify_idempotent"},
    "cloud.check_cloud_creds": {"verify_idempotent"},
    "cloud.s3_sync": {"cloud.check_cloud_creds"},
    "cloud.load_snowflake": {"cloud.s3_sync"},
    "cloud.dbt_snowflake": {"cloud.load_snowflake"},
    "cloud.verify_parity": {"rag_build", "cloud.dbt_snowflake"},
}

NETWORK_TASKS = {
    "ingest",
    "cloud.s3_sync",
    "cloud.load_snowflake",
    "cloud.dbt_snowflake",
    "cloud.verify_parity",
    "rag_build",
}


@pytest.fixture(scope="module")
def dag_bag() -> DagBag:
    # Airflow 3.3's DagBag has no include_examples kwarg; example
    # loading is disabled via AIRFLOW__CORE__LOAD_EXAMPLES above
    return DagBag(dag_folder=DAG_FOLDER)


@pytest.fixture(scope="module")
def dag(dag_bag: DagBag):
    return dag_bag.dags[DAG_ID]


def test_imports_clean(dag_bag: DagBag) -> None:
    assert dag_bag.import_errors == {}, f"import errors: {dag_bag.import_errors}"
    assert set(dag_bag.dag_ids) == {DAG_ID}


def test_task_ids_match_documented_order(dag) -> None:
    assert {t.task_id for t in dag.tasks} == set(EXPECTED_UPSTREAMS)


def test_dependencies_match_documented_order(dag) -> None:
    actual = {t.task_id: set(t.upstream_task_ids) for t in dag.tasks}
    assert actual == EXPECTED_UPSTREAMS


def test_no_schedule_surprises(dag) -> None:
    # "@daily" resolves to a CronTriggerTimetable on midnight cron
    assert dag.timetable.expression == "0 0 * * *"
    assert dag.catchup is False
    assert dag.max_active_runs == 1


def test_trigger_rules(dag) -> None:
    # local-first graph: nothing upstream of the local path can skip,
    # so EVERY task keeps the default all_success rule; verify_parity
    # inherits the no-creds skip from dbt_snowflake through it
    rules = {t.task_id: t.trigger_rule.value for t in dag.tasks}
    for task_id, rule in rules.items():
        assert rule == "all_success", f"{task_id} has surprise rule {rule}"


def test_retry_policy(dag) -> None:
    # network tasks retry with backoff; deterministic local tasks never
    for task in dag.tasks:
        if task.task_id in NETWORK_TASKS:
            assert task.retries == 2, f"{task.task_id} should retry"
            assert task.retry_exponential_backoff
        else:
            assert task.retries == 0, f"{task.task_id} should not retry"


# task_id -> exact make targets its bash_command may call. The DAG must
# only ever orchestrate make — and never the forbidden ones below.
EXPECTED_MAKE_TARGETS: dict[str, list[str]] = {
    "ingest": ["ingest"],
    "parse": ["parse"],
    "circuit_breaker": ["circuit-breaker"],
    "cloud.s3_sync": ["s3-sync"],
    "cloud.load_snowflake": ["load-snowflake"],
    "cloud.dbt_snowflake": ["dbt-snowflake"],
    "dbt_duckdb": ["snapshot", "dbt"],
    "verify_idempotent": ["verify-idempotent"],
    "rag_build": ["rag-build"],
    "cloud.verify_parity": ["verify-parity"],
}

# snapshot-day0 is a one-time bootstrap whose re-run corrupts the demo
# transitions; reset destroys the snapshot history (DECISIONS.md
# 2026-08-14) — neither may ever appear in the DAG
FORBIDDEN_MAKE_TARGETS = {"snapshot-day0", "reset"}


def _make_targets(bash_command: str) -> list[str]:
    return re.findall(r"make ([a-z0-9-]+)", bash_command)


def test_bash_commands_call_expected_make_targets(dag) -> None:
    actual = {
        t.task_id: _make_targets(t.bash_command)
        for t in dag.tasks
        if isinstance(t, BashOperator)
    }
    assert actual == EXPECTED_MAKE_TARGETS


def test_no_forbidden_make_target(dag) -> None:
    for task in dag.tasks:
        if isinstance(task, BashOperator):
            called = set(_make_targets(task.bash_command))
            assert not called & FORBIDDEN_MAKE_TARGETS, (
                f"{task.task_id} calls forbidden target(s): "
                f"{called & FORBIDDEN_MAKE_TARGETS}"
            )


def test_all_make_targets_exist(dag) -> None:
    # a bash_command typo would otherwise surface only inside Docker
    makefile = (REPO_ROOT / "Makefile").read_text()
    defined = set(re.findall(r"^([a-z0-9-]+):", makefile, flags=re.MULTILINE))
    for task in dag.tasks:
        if isinstance(task, BashOperator):
            for target in _make_targets(task.bash_command):
                assert target in defined, (
                    f"{task.task_id} calls undefined make target {target}"
                )


def test_operator_types(dag) -> None:
    for task in dag.tasks:
        if task.task_id == "cloud.check_cloud_creds":
            assert isinstance(task, ShortCircuitOperator)
        else:
            assert isinstance(task, BashOperator), task.task_id


def test_short_circuit_respects_trigger_rules(dag) -> None:
    # the skip must flow through trigger rules (not flatten downstream
    # unconditionally) so verify_parity inherits it via all_success;
    # also keeps the gate safe if anything non-cloud ever lands below it
    gate = dag.get_task("cloud.check_cloud_creds")
    assert gate.ignore_downstream_trigger_rules is False


def test_execution_timeouts(dag) -> None:
    # max_active_runs=1: one hung task blocks the schedule, so every
    # task needs a timeout — 30 min network, 15 min local
    for task in dag.tasks:
        minutes = 30 if task.task_id in NETWORK_TASKS else 15
        assert task.execution_timeout == timedelta(minutes=minutes), (
            f"{task.task_id}: {task.execution_timeout}"
        )


def test_start_date_and_no_depends_on_past(dag) -> None:
    assert dag.start_date == datetime(2026, 8, 15, tzinfo=timezone.utc)
    for task in dag.tasks:
        assert task.depends_on_past is False, task.task_id


def test_cloud_creds_gate_callable(dag, monkeypatch, capsys) -> None:
    gate = dag.get_task("cloud.check_cloud_creds").python_callable
    required = (
        "SNOWFLAKE_ACCOUNT",
        "SNOWFLAKE_USER",
        "SNOWFLAKE_PASSWORD",
        "AWS_PROFILE",
    )

    for key in required:
        monkeypatch.delenv(key, raising=False)
    assert gate() is False
    out = capsys.readouterr().out
    for key in required:
        assert key in out  # skip reason names every missing var

    sentinel = "value-that-must-never-be-printed"
    for key in required:
        monkeypatch.setenv(key, sentinel)
    monkeypatch.setenv("SNOWFLAKE_PASSWORD", "")
    assert gate() is False  # empty string counts as missing
    out = capsys.readouterr().out
    assert "SNOWFLAKE_PASSWORD" in out
    assert sentinel not in out  # names only, never values

    monkeypatch.setenv("SNOWFLAKE_PASSWORD", sentinel)
    assert gate() is True
    assert sentinel not in capsys.readouterr().out
