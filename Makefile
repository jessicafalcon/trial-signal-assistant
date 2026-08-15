VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
# CI overrides with PYTEST=pytest / PY=python / DBT=dbt (no venv there)
PYTEST ?= $(VENV)/bin/pytest
DBT ?= $(VENV)/bin/dbt
DBT_FLAGS := --project-dir dbt_project --profiles-dir dbt_project --target duckdb
# snapshot state read through dbt itself (no direct duckdb import; stdlib
# json only): row count + fingerprint of the ordered dbt_scd_id set, so a
# same-count churn (row closed + row opened) still fails verify-idempotent
SNAP_STATE = $(DBT) --quiet show --inline "select count(*) as n, coalesce(md5(string_agg(dbt_scd_id, ',' order by dbt_scd_id)), '0') as fp from {{ ref('snap_trial_status') }}" --output json $(DBT_FLAGS) | $(PY) -c "import json, sys; d = json.load(sys.stdin)['show'][0]; print(d['n'], d['fp'])"
MART_COUNT = $(DBT) --quiet show --inline "select count(*) as n from {{ ref('mart_trial_status_changes') }}" --output json $(DBT_FLAGS) | $(PY) -c "import json, sys; print(json.load(sys.stdin)['show'][0]['n'])"

.PHONY: setup test ingest parse dbt dbt-snowflake eval lint snapshot-day0 snapshot verify-idempotent verify-day0-count reset

setup:
	python3 -m venv $(VENV)
	$(PIP) install -r requirements.txt
	$(VENV)/bin/pre-commit install
	$(VENV)/bin/pre-commit install --hook-type pre-push
	@command -v gitleaks >/dev/null || echo "WARNING: gitleaks not installed (brew install gitleaks); scripts/secrets_audit.sh check (d) will fail"

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

dbt-snowflake:
	@echo "not implemented until phase 4"

eval:
	@echo "not implemented until phase 5"

lint:
	$(VENV)/bin/pre-commit run --all-files
