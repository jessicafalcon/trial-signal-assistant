"""Guards on the cloud targets (phase 4, ruling F16).

Both tests are network-free by construction: each path under test fails
before any connection is attempted.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DBT = REPO_ROOT / ".venv" / "bin" / "dbt"
CREDS = ("SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_PASSWORD")


def _env_without_creds() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k not in CREDS}


@pytest.mark.parametrize("target", ["dbt-snowflake", "load-snowflake"])
def test_preflight_fails_closed_without_credentials(target: str) -> None:
    result = subprocess.run(
        ["make", target],
        cwd=REPO_ROOT,
        env=_env_without_creds(),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "ERROR: SNOWFLAKE_ACCOUNT / SNOWFLAKE_USER / SNOWFLAKE_PASSWORD" in output
    # dbt must never have started (it always logs a "Running with dbt" banner)
    assert "Running with dbt" not in output


# --- R2 partition selection (SPEC-06): scripts/load_snowflake.sh ---
# DBT=/bin/echo stubs the dbt invocation, so every case is network-free
# and asserts exactly which partitions the script would load.

LOAD_SCRIPT = REPO_ROOT / "scripts" / "load_snowflake.sh"


def _run_load(tmp_path: Path, partitions: list[str], **extra_env: str):
    parsed = tmp_path / "data" / "parsed"
    parsed.mkdir(parents=True)
    for p in partitions:
        (parsed / f"ingest_date={p}").mkdir()
    env = {
        **_env_without_creds(),
        "SNOWFLAKE_ACCOUNT": "dummy",
        "SNOWFLAKE_USER": "dummy",
        "SNOWFLAKE_PASSWORD": "dummy",
        "DBT": "/bin/echo",
        "DATE": "",
        "ALL": "",
        **extra_env,
    }
    return subprocess.run(
        [str(LOAD_SCRIPT)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_load_defaults_to_latest_partition(tmp_path: Path) -> None:
    result = _run_load(tmp_path, ["2026-08-13", "2026-08-14", "2026-08-15"])
    assert result.returncode == 0
    assert 'partition: "2026-08-15"' in result.stdout
    assert "2026-08-14" not in result.stdout


def test_load_all_loads_every_partition_ascending(tmp_path: Path) -> None:
    result = _run_load(tmp_path, ["2026-08-14", "2026-08-13", "2026-08-15"], ALL="1")
    assert result.returncode == 0
    positions = [
        result.stdout.index(f'partition: "{p}"')
        for p in ["2026-08-13", "2026-08-14", "2026-08-15"]
    ]
    assert positions == sorted(positions)


def test_load_date_override_picks_one(tmp_path: Path) -> None:
    result = _run_load(tmp_path, ["2026-08-14", "2026-08-15"], DATE="2026-08-14")
    assert result.returncode == 0
    assert 'partition: "2026-08-14"' in result.stdout
    assert "2026-08-15" not in result.stdout


def test_load_rejects_malformed_date(tmp_path: Path) -> None:
    result = _run_load(tmp_path, ["2026-08-15"], DATE="2026-8-1;")
    assert result.returncode != 0
    assert "partition must be YYYY-MM-DD" in result.stderr
    assert "run-operation" not in result.stdout  # dbt never invoked


def test_load_fails_loudly_with_no_partitions(tmp_path: Path) -> None:
    # regression: under set -e a failing ls used to abort before the
    # error message could print (empty log in the DAG)
    result = _run_load(tmp_path, [])
    assert result.returncode != 0
    assert "no partitions found" in result.stderr


@pytest.mark.skipif(not DBT.exists(), reason="no venv dbt (CI test job has none)")
def test_load_macro_refuses_non_snowflake_target() -> None:
    result = subprocess.run(
        [
            str(DBT),
            "run-operation",
            "load_raw_trials",
            "--project-dir",
            "dbt_project",
            "--profiles-dir",
            "dbt_project",
            "--target",
            "duckdb",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert result.returncode != 0
    assert "snowflake-only" in result.stdout + result.stderr
