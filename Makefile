VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
# CI overrides with PYTEST=pytest / PY=python / DBT=dbt (no venv there)
PYTEST ?= $(VENV)/bin/pytest
DBT ?= $(VENV)/bin/dbt
DBT_FLAGS := --project-dir dbt_project --profiles-dir dbt_project --target duckdb
# counts SCD2 rows in the snapshot table (read-only; used by verify-idempotent)
SNAP_COUNT = $(PY) -c "import duckdb; print(duckdb.connect('dbt_project/trial_signal.duckdb', read_only=True).sql('select count(*) from snap_trial_status').fetchone()[0])"

.PHONY: setup test ingest parse dbt dbt-snowflake eval lint snapshot-day0 snapshot verify-idempotent reset

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
# fail if the snapshot row count changed.
verify-idempotent:
	@before=$$($(SNAP_COUNT)) && \
	$(DBT) snapshot $(DBT_FLAGS) && \
	after=$$($(SNAP_COUNT)) && \
	echo "snapshot rows: before=$$before after=$$after" && \
	if [ "$$before" != "$$after" ]; then echo "FAIL: snapshot re-run changed row count"; exit 1; fi

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
