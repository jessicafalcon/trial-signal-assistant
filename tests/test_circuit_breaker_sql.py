"""Boundary tests for the R1 circuit-breaker SQL (SPEC-06).

Runs the singular test's SQL against synthetic partitions in an
in-memory DuckDB — same pattern as the RAG mart-SQL tests: no dbt, no
network, CI-safe. The jinja is rendered by plain substitution; the
assertion below fails loudly if the file's ref/var spelling changes.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SQL_PATH = (
    REPO_ROOT / "dbt_project" / "tests" / "assert_latest_partition_not_collapsed.sql"
)
PROJECT_YML = REPO_ROOT / "dbt_project" / "dbt_project.yml"


def _rendered_sql() -> str:
    ratio = yaml.safe_load(PROJECT_YML.read_text())["vars"]["circuit_breaker_min_ratio"]
    sql = SQL_PATH.read_text()
    sql = sql.replace("{{ ref('stg_clinical_trials') }}", "stg_clinical_trials")
    sql = sql.replace("{{ var('circuit_breaker_min_ratio') }}", str(ratio))
    assert "{{" not in sql, "unrendered jinja — did the ref/var spelling change?"
    return sql


def _breaker_rows(partitions: dict[str, int]) -> list[tuple]:
    con = duckdb.connect()
    con.execute("create table stg_clinical_trials (ingest_date date)")
    for day, n in partitions.items():
        con.execute(
            f"insert into stg_clinical_trials select date '{day}' from range({n})"
        )
    return con.execute(_rendered_sql()).fetchall()


@pytest.mark.parametrize(
    ("partitions", "fires"),
    [
        # single partition: no prior to compare — passes
        ({"2026-08-14": 1738}, False),
        # growth passes
        ({"2026-08-14": 1738, "2026-08-15": 1800}, False),
        # exactly at the 0.8 threshold passes (strict <, not <=)
        ({"2026-08-14": 1000, "2026-08-15": 800}, False),
        # one row under the threshold fires
        ({"2026-08-14": 1000, "2026-08-15": 799}, True),
        # collapsed ingest fires
        ({"2026-08-14": 1738, "2026-08-15": 1}, True),
        # only the LATEST pair is checked: a historical dip that later
        # recovered must not fail forever
        ({"2026-08-12": 1000, "2026-08-13": 100, "2026-08-14": 1000}, False),
    ],
)
def test_breaker_boundaries(partitions: dict[str, int], fires: bool) -> None:
    rows = _breaker_rows(partitions)
    assert bool(rows) is fires, f"partitions={partitions} rows={rows}"
