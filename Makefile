VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
# CI overrides with PYTEST=pytest / PY=python / DBT=dbt (no venv there)
PYTEST ?= $(VENV)/bin/pytest
DBT ?= $(VENV)/bin/dbt

.PHONY: setup test ingest parse dbt dbt-snowflake eval lint

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
	$(DBT) build --project-dir dbt_project --profiles-dir dbt_project --target duckdb

dbt-snowflake:
	@echo "not implemented until phase 4"

eval:
	@echo "not implemented until phase 5"

lint:
	$(VENV)/bin/pre-commit run --all-files
