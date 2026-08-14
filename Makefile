VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
# CI overrides with PYTEST=pytest (no venv there)
PYTEST ?= $(VENV)/bin/pytest

.PHONY: setup test ingest dbt dbt-snowflake eval lint

setup:
	python3 -m venv $(VENV)
	$(PIP) install -r requirements.txt
	$(VENV)/bin/pre-commit install
	@command -v gitleaks >/dev/null || echo "WARNING: gitleaks not installed (brew install gitleaks); scripts/secrets_audit.sh check (d) will fail"

test:
	$(PYTEST) tests/test_parser.py -v

ingest:
	$(PY) -m ingest.fetch_clinical_trials

dbt:
	@echo "not implemented until phase 2"

dbt-snowflake:
	@echo "not implemented until phase 4"

eval:
	@echo "not implemented until phase 5"

lint:
	$(VENV)/bin/pre-commit run --all-files
