VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: setup test ingest dbt dbt-snowflake eval lint

setup:
	python3 -m venv $(VENV)
	$(PIP) install -r requirements.txt
	$(VENV)/bin/pre-commit install

test:
	$(VENV)/bin/pytest tests/test_parser.py -v

ingest:
	@echo "not implemented until phase 1"

dbt:
	@echo "not implemented until phase 2"

dbt-snowflake:
	@echo "not implemented until phase 4"

eval:
	@echo "not implemented until phase 5"

lint:
	$(VENV)/bin/pre-commit run --all-files
