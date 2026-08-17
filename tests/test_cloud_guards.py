"""Guards on the cloud targets (phase 4, ruling F16).

Both tests are network-free by construction: each path under test fails
before any connection is attempted.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DBT = REPO_ROOT / ".venv" / "bin" / "dbt"
CREDS = ("SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_PASSWORD")


def _env_without_creds() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k not in CREDS}


# every credentialed make target, each invoked directly. The plain
# snapshot-snowflake case is satisfiable by either preflight layer
# (its circuit-breaker-snowflake prerequisite runs first), so the -o
# case assumes the prerequisite up to date and pins the recipe's OWN
# preflight in isolation — a refactor dropping either layer fails one
# of the two cases (security finding 2 ruling, 2026-08-17)
@pytest.mark.parametrize(
    "command",
    [
        ["make", "dbt-snowflake"],
        ["make", "load-snowflake"],
        ["make", "snapshot-day0-snowflake"],
        ["make", "circuit-breaker-snowflake"],
        ["make", "snapshot-snowflake"],
        ["make", "-o", "circuit-breaker-snowflake", "snapshot-snowflake"],
        ["make", "freshness-snowflake"],
    ],
    ids=lambda command: " ".join(command[1:]),
)
def test_preflight_fails_closed_without_credentials(command: list[str]) -> None:
    result = subprocess.run(
        command,
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


# --- phase-7 checklist: dual-target source resolution (F16 deferral) ---
# dbt parse never opens a connection, and the subprocess env below is a
# minimal explicit dict — no copy of the caller's environment, so no
# credential can reach the subprocess or its output (phase-7 review
# ruling 5: "credential-free" is literal). The profile's env_var()
# calls all carry defaults, so no SNOWFLAKE_* var is needed to parse.
# DBT_TARGET_PATH and DBT_LOG_PATH point at tmp_path so the test
# neither reads nor poisons the host's target/ partial-parse cache and
# writes no artifacts outside tmp_path at all.


@pytest.mark.skipif(not DBT.exists(), reason="no venv dbt (CI test job has none)")
@pytest.mark.parametrize(
    ("target", "schema", "identifier"),
    [("duckdb", "main", "clinical_trials"), ("snowflake", "raw", "trials")],
)
def test_source_resolves_per_target(
    tmp_path: Path, target: str, schema: str, identifier: str
) -> None:
    env = {
        "PATH": os.environ["PATH"],
        "HOME": os.environ["HOME"],
        "DBT_TARGET_PATH": str(tmp_path),
        "DBT_LOG_PATH": str(tmp_path),
    }
    result = subprocess.run(
        [
            str(DBT),
            "parse",
            "--project-dir",
            "dbt_project",
            "--profiles-dir",
            "dbt_project",
            "--target",
            target,
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    [key] = [k for k in manifest["sources"] if k.endswith(".parsed.clinical_trials")]
    node = manifest["sources"][key]
    assert node["schema"] == schema
    assert node["identifier"] == identifier
    # freshness thresholds live under the table's config: key (the dbt
    # 1.10+ location) — a wrong nesting silently drops them and make
    # freshness would pass with nothing to check (finding-8 ruling,
    # 2026-08-17), so pin them in the parsed manifest on both targets
    freshness = node["freshness"]
    assert freshness["warn_after"] == {"count": 2, "period": "day"}
    assert freshness["error_after"] == {"count": 7, "period": "day"}
    if target == "duckdb":
        # the read path stays the FIXED literal (injection ruling,
        # DECISIONS.md 2026-08-14) — a parameterized value here is a bug
        assert "read_parquet('data/parsed/ingest_date=*/trials.parquet')" in json.dumps(
            node
        )


def test_s3_bucket_and_prefix_match_terraform() -> None:
    # the Makefile duplicates terraform's bucket/prefix defaults because
    # the DAG container running make s3-sync has no terraform binary to
    # consume `terraform output` from; this pins the pairs equal so
    # drift fails loudly instead (phase-7 ruling on F10, DECISIONS.md)
    makefile = (REPO_ROOT / "Makefile").read_text()
    variables_tf = (REPO_ROOT / "terraform" / "variables.tf").read_text()
    s3_tf = (REPO_ROOT / "terraform" / "s3.tf").read_text()

    mk_bucket = re.search(r"^S3_BUCKET \?= (\S+)$", makefile, re.MULTILINE)
    mk_prefix = re.search(r"^S3_PREFIX \?= (\S+)$", makefile, re.MULTILINE)
    tf_bucket = re.search(
        r'variable "s3_bucket_name" \{.*?default\s*=\s*"([^"]+)"',
        variables_tf,
        re.DOTALL,
    )
    tf_prefix = re.search(r'parsed_prefix\s*=\s*"([^"]+)"', s3_tf)
    assert mk_bucket and mk_prefix and tf_bucket and tf_prefix
    assert mk_bucket.group(1) == tf_bucket.group(1)
    assert mk_prefix.group(1) == tf_prefix.group(1)


# --- destructive-path gates (security finding 3 ruling, 2026-08-17):
# the reviewer's manual probes converted to regression tests — all
# network-free, every path fails before any connection or drop.

REBASELINE_SCRIPT = REPO_ROOT / "scripts" / "rebaseline_snowflake_snapshot.sh"


@pytest.mark.parametrize(
    ("confirm", "expected"),
    [
        # no token: gate refuses before anything else runs
        (None, "Re-run with CONFIRM_REBASELINE=1"),
        # strict =1 matching: truthy-but-not-1 must refuse too — the
        # loosening a well-meaning future edit would introduce
        ("true", "Re-run with CONFIRM_REBASELINE=1"),
        # token set without creds: preflight refuses before the drop
        ("1", "ERROR: SNOWFLAKE_ACCOUNT / SNOWFLAKE_USER / SNOWFLAKE_PASSWORD"),
    ],
    ids=["no-confirm", "confirm-true", "confirm-1-no-creds"],
)
def test_rebaseline_gates_fail_closed(confirm: str | None, expected: str) -> None:
    env = _env_without_creds()
    env.pop("CONFIRM_REBASELINE", None)
    # the gate answers ONLY to its own token (per-gate-confirm ruling):
    # a legacy shared CONFIRM must never satisfy it
    env["CONFIRM"] = "1"
    if confirm is not None:
        env["CONFIRM_REBASELINE"] = confirm
    result = subprocess.run(
        [str(REBASELINE_SCRIPT)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert expected in output
    # dbt never started: no connection, no drop attempted
    assert "Running with dbt" not in output


# --- bootstrap guard probe pair (post-merge review finding,
# 2026-08-17): both guards' branches pinned network-free via a stub
# dbt whose `show --inline` probe behaves per case; every other dbt
# invocation exits 0, so a "proceeds" case runs its recipe harmlessly.

STUB_DBT = """#!/bin/sh
case "$*" in
    *"show --inline"*) {probe} ;;
    *) exit 0 ;;
esac
"""

PROBE_TABLE_EXISTS = "exit 0"
PROBE_TABLE_ABSENT = (
    'echo "002003 (42S02): Object does not exist or not authorized."; exit 1'
)
PROBE_INCONCLUSIVE = 'echo "250001: network unreachable"; exit 1'


def _run_guarded_target(
    tmp_path: Path, target: str, probe: str, **extra_env: str
) -> subprocess.CompletedProcess[str]:
    stub = tmp_path / "dbt-stub"
    stub.write_text(STUB_DBT.format(probe=probe))
    stub.chmod(0o755)
    # allowlist env, matching test_source_resolves_per_target's
    # "credential-free is literal" posture (security note 4 ruling):
    # nothing from the operator's shell — no ambient override tokens,
    # no real credentials — can reach the make subprocess
    env = {
        "PATH": os.environ["PATH"],
        "HOME": os.environ["HOME"],
        "SNOWFLAKE_ACCOUNT": "dummy",
        "SNOWFLAKE_USER": "dummy",
        "SNOWFLAKE_PASSWORD": "dummy",
        "DBT": str(stub),
    }
    env.update(extra_env)
    return subprocess.run(
        ["make", target],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


@pytest.mark.parametrize(
    ("probe", "confirm", "ok", "expect", "runs_seed"),
    [
        # table exists, no override: refuse before the seed
        (PROBE_TABLE_EXISTS, None, False, "already exists", False),
        # reviewer-specified escape hatch: the gate's OWN token
        # proceeds, loudly
        (PROBE_TABLE_EXISTS, "1", True, "WARNING: CONFIRM_DAY0_OVERWRITE=1", True),
        # absent (002003): the intended bootstrap path proceeds
        (PROBE_TABLE_ABSENT, None, True, "", True),
        # inconclusive probe: distinct refusal, never the seed
        (PROBE_INCONCLUSIVE, None, False, "could not be evaluated", False),
    ],
    ids=["exists-refuses", "exists-confirm-1", "absent-proceeds", "inconclusive"],
)
def test_day0_snowflake_inverse_guard(
    tmp_path: Path,
    probe: str,
    confirm: str | None,
    ok: bool,
    expect: str,
    runs_seed: bool,
) -> None:
    # a legacy shared CONFIRM is always present and must never satisfy
    # the gate (per-gate-confirm ruling)
    extra = {"CONFIRM": "1"}
    if confirm is not None:
        extra["CONFIRM_DAY0_OVERWRITE"] = confirm
    result = _run_guarded_target(tmp_path, "snapshot-day0-snowflake", probe, **extra)
    output = result.stdout + result.stderr
    assert (result.returncode == 0) is ok, output
    assert expect in output
    assert ("seed --select seed_synthetic_day0" in output) is runs_seed


@pytest.mark.parametrize(
    ("probe", "ok", "expect", "runs_snapshot"),
    [
        # absent/unauthorized: bootstrap-first refusal, never snapshots
        (PROBE_TABLE_ABSENT, False, "absent OR not authorized", False),
        # inconclusive probe: distinct refusal, never snapshots
        (PROBE_INCONCLUSIVE, False, "could not be evaluated", False),
        # table exists: the guarded live snapshot proceeds
        (PROBE_TABLE_EXISTS, True, "", True),
    ],
    ids=["absent-refuses", "inconclusive", "exists-proceeds"],
)
def test_snapshot_snowflake_forward_guard(
    tmp_path: Path, probe: str, ok: bool, expect: str, runs_snapshot: bool
) -> None:
    result = _run_guarded_target(tmp_path, "snapshot-snowflake", probe)
    output = result.stdout + result.stderr
    assert (result.returncode == 0) is ok, output
    assert expect in output
    assert ("run --select +snap_trial_status" in output) is runs_snapshot


@pytest.mark.skipif(not DBT.exists(), reason="no venv dbt (CI test job has none)")
def test_drop_snapshot_macro_refuses_non_snowflake_target() -> None:
    result = subprocess.run(
        [
            str(DBT),
            "run-operation",
            "drop_snapshot_table",
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
