VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
# CI overrides with PYTEST=pytest / PY=python / DBT=dbt (no venv there)
PYTEST ?= $(VENV)/bin/pytest
DBT ?= $(VENV)/bin/dbt
DBT_FLAGS := --project-dir dbt_project --profiles-dir dbt_project --target duckdb
DBT_SNOWFLAKE_FLAGS := --project-dir dbt_project --profiles-dir dbt_project --target snowflake

# cloud target (phase 4). Bucket/prefix duplicate terraform's
# variables.tf s3_bucket_name default and s3.tf parsed_prefix local —
# keep the three in sync; override here if the terraform vars were
# overridden (single-sourcing via terraform output: phase 7 checklist).
S3_BUCKET ?= trial-signal-raw-landing
S3_PREFIX ?= parsed
# Non-secret connection facts pinned to the terraform-created objects,
# so the demo provably runs as TRANSFORMER on the XS warehouse whatever
# the caller's .env says. Secrets (SNOWFLAKE_ACCOUNT/USER/PASSWORD)
# come only from the caller's environment and are never echoed.
SNOWFLAKE_CONN = SNOWFLAKE_ROLE=TRANSFORMER SNOWFLAKE_WAREHOUSE=TRIAL_SIGNAL_WH SNOWFLAKE_DATABASE=TRIAL_SIGNAL SNOWFLAKE_SCHEMA=ANALYTICS
# fail fast on missing creds. NOTE: dbt itself auto-loads .env from the
# cwd (dbt 1.12 dotenv), but make recipes do not see it — this guard
# makes the make path fail closed instead of leaning on that behavior.
define snowflake_preflight
	@if [ -z "$$SNOWFLAKE_ACCOUNT" ] || [ -z "$$SNOWFLAKE_USER" ] || [ -z "$$SNOWFLAKE_PASSWORD" ]; then \
		echo "ERROR: SNOWFLAKE_ACCOUNT / SNOWFLAKE_USER / SNOWFLAKE_PASSWORD not set. Load them first: set -a; source .env; set +a"; \
		exit 1; \
	fi
endef
# snapshot state read through dbt itself (no direct duckdb import; stdlib
# json only): row count + fingerprint of the ordered dbt_scd_id set, so a
# same-count churn (row closed + row opened) still fails verify-idempotent
SNAP_STATE = $(DBT) --quiet show --inline "select count(*) as n, coalesce(md5(string_agg(dbt_scd_id, ',' order by dbt_scd_id)), '0') as fp from {{ ref('snap_trial_status') }}" --output json $(DBT_FLAGS) | $(PY) -c "import json, sys; d = json.load(sys.stdin)['show'][0]; print(d['n'], d['fp'])"
MART_COUNT = $(DBT) --quiet show --inline "select count(*) as n from {{ ref('mart_trial_status_changes') }}" --output json $(DBT_FLAGS) | $(PY) -c "import json, sys; print(json.load(sys.stdin)['show'][0]['n'])"

.PHONY: setup test ingest parse dbt dbt-snowflake eval lint snapshot-day0 snapshot verify-idempotent verify-day0-count reset s3-sync load-snowflake

setup:
	python3 -m venv $(VENV)
	$(PIP) install -r requirements.txt
	$(VENV)/bin/pre-commit install
	$(VENV)/bin/pre-commit install --hook-type pre-push
	@command -v gitleaks >/dev/null || echo "WARNING: gitleaks not installed (brew install gitleaks); scripts/secrets_audit.sh check (d) will fail"
	@command -v aws >/dev/null || echo "WARNING: aws CLI not installed (brew install awscli); make s3-sync will fail"
	@command -v terraform >/dev/null || echo "WARNING: terraform not installed (brew install hashicorp/tap/terraform); see terraform/README.md"

test:
	$(PYTEST) tests -v

ingest:
	$(PY) -m ingest.fetch_clinical_trials

# FIXTURES=1 parses tests/fixtures/ (CI mode); DATE=YYYY-MM-DD picks a partition
parse:
	$(PY) -m ingest.parse_to_parquet $(if $(FIXTURES),--fixtures,) $(if $(DATE),--date $(DATE),)

dbt:
	$(DBT) build $(DBT_FLAGS)

# load the labeled synthetic day-0 seed and snapshot from it.
# FIXTURES=1 selects the fixture-scoped seed variant (CI corpus).
snapshot-day0:
	$(DBT) seed $(DBT_FLAGS)
	$(DBT) snapshot $(DBT_FLAGS) --vars '{snapshot_source: seed, day0_seed_scope: $(if $(FIXTURES),fixtures,corpus)}'

# live snapshot (snapshot_source defaults to 'live'). The dbt run first
# builds the staging views the snapshot reads — from a clean database,
# dbt snapshot alone would fail because they don't exist yet.
snapshot:
	$(DBT) run --select +snap_trial_status $(DBT_FLAGS)
	$(DBT) snapshot $(DBT_FLAGS)

# idempotency proof: re-run the live snapshot against unchanged data and
# fail if the snapshot changed (row count or dbt_scd_id fingerprint).
verify-idempotent:
	@before=$$($(SNAP_STATE)) && \
	$(DBT) snapshot $(DBT_FLAGS) && \
	after=$$($(SNAP_STATE)) && \
	echo "snapshot rows+fingerprint: before=[$$before] after=[$$after]" && \
	if [ "$$before" != "$$after" ]; then echo "FAIL: snapshot re-run changed state"; exit 1; fi

# asserts the mart holds exactly the 4 seeded day-0 transitions; run by
# CI after the fixture-mode sequence (true locally after DONE as well)
verify-day0-count:
	@n=$$($(MART_COUNT)) && \
	echo "mart_trial_status_changes rows: $$n" && \
	if [ "$$n" != "4" ]; then echo "FAIL: expected exactly 4 day-0 transitions, got $$n"; exit 1; fi

# clean state: the DONE sequence for SPEC-03 starts from `make reset`
# (delete the local DuckDB file; dbt recreates it).
reset:
	rm -f dbt_project/trial_signal.duckdb

# push parsed parquet partitions to the S3 landing bucket. sync is
# content-aware: a byte-identical partition transfers 0 files on
# re-run; a re-parse rewrites the file and IS re-uploaded.
s3-sync:
	@if [ -z "$$AWS_PROFILE" ]; then \
		echo "ERROR: AWS_PROFILE not set. Load it first: set -a; source .env; set +a"; \
		exit 1; \
	fi
	aws s3 sync data/parsed/ s3://$(S3_BUCKET)/$(S3_PREFIX)/

# COPY INTO RAW.TRIALS from the external stage (dbt macro
# load_raw_trials). Idempotent for byte-identical files via COPY's
# load history; re-parsed files re-load (see the macro header).
# preflight + pinned connection facts live in the script itself, so a
# direct invocation behaves identically to this target.
load-snowflake:
	DBT=$(DBT) scripts/load_snowflake.sh

# same dbt project on the snowflake target. Snapshot machinery is
# duckdb-only this phase (DECISIONS.md): exclude the snapshot and its
# descendants, and the day-0 seeds.
dbt-snowflake:
	$(snowflake_preflight)
	$(SNOWFLAKE_CONN) $(DBT) build $(DBT_SNOWFLAKE_FLAGS) --exclude snap_trial_status+ resource_type:seed

eval:
	@echo "not implemented until phase 5"

lint:
	$(VENV)/bin/pre-commit run --all-files
