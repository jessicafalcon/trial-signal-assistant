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
