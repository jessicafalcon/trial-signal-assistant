VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
# CI overrides with PYTEST=pytest / PY=python / DBT=dbt (no venv there)
PYTEST ?= $(VENV)/bin/pytest
DBT ?= $(VENV)/bin/dbt
DBT_FLAGS := --project-dir dbt_project --profiles-dir dbt_project --target duckdb
DBT_SNOWFLAKE_FLAGS := --project-dir dbt_project --profiles-dir dbt_project --target snowflake

# cloud target (phase 4). Bucket/prefix duplicate terraform's
# variables.tf s3_bucket_name default and s3.tf parsed_prefix local;
# tests/test_cloud_guards.py asserts the pairs stay equal (loud drift
# instead of runtime coupling — the DAG container that runs s3-sync
# has no terraform binary, so `terraform output` can't be the source
# there; DECISIONS.md phase-7 entry). Override here only if the
# terraform vars were overridden at apply time.
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

.PHONY: setup test dag-verify ingest parse dbt dbt-snowflake eval lint snapshot-day0 snapshot circuit-breaker verify-idempotent verify-day0-count verify-parity reset s3-sync load-snowflake rag-build ask

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

# DAG integrity without Docker (DagBag import + structure). airflow is
# a test-only dep, isolated in airflow/requirements-dagtest.txt (owner
# ruling): installed here explicitly, never by make setup, and pinned
# transitively via Airflow's published constraints file for the venv's
# Python. Airflow 3.3.0 publishes constraints for 3.11-3.13 only —
# other interpreters fail loudly here (owner ruling; README "Setup"
# states the venv requirement). DAG_TESTS_REQUIRED=1 turns the
# no-airflow skip into a loud failure.
dag-verify:
	@pyver=$$($(PY) -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")') && \
	case "$$pyver" in \
		3.11|3.12|3.13) ;; \
		*) echo "ERROR: no Airflow 3.3.0 constraints file for Python $$pyver (published: 3.11-3.13)."; \
		   echo "Recreate the venv with a supported Python (README Setup), then re-run."; \
		   exit 1;; \
	esac && \
	$(PIP) install --quiet -r airflow/requirements-dagtest.txt \
		--constraint "https://raw.githubusercontent.com/apache/airflow/constraints-3.3.0/constraints-$$pyver.txt"
	@# the constraints file serves Airflow's test matrix, not this
	@# repo's stack: it can move shared transitive deps (observed
	@# 2026-08-15: cryptography 48.0.1 broke pyopenssl/snowflake).
	@# Restore the ranges both stacks accept, then fail loudly on any
	@# remaining metadata conflict.
	$(PIP) install --quiet 'cryptography>=49,<51' 'pathspec>=0.9,<1.1' 'certifi<2025.4.26' 'more-itertools>=10.0.0,<11.0'
	$(PIP) check
	DAG_TESTS_REQUIRED=1 $(PYTEST) tests/test_dag_integrity.py -v

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

# circuit breaker (R1): the snapshot invalidates hard deletes on live
# runs, so a collapsed ingest must never reach it. Fails if the latest
# partition holds < circuit_breaker_min_ratio of the prior one's rows.
# dbt build (not test): +selector builds the staging view first, so
# this is self-sufficient on a clean database and as the DAG task.
circuit-breaker:
	$(DBT) build --select +assert_latest_partition_not_collapsed $(DBT_FLAGS)

# live snapshot (snapshot_source defaults to 'live'). circuit-breaker
# runs first (never snapshot a collapsed ingest) and builds the
# snapshot's staging ancestors as a side effect; the dbt run then
# builds the rest of the snapshot's input (stg_trials_current).
snapshot: circuit-breaker
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
# (delete the local DuckDB file; dbt recreates it). The path is read
# from profiles.yml — the single place it is declared (phase-7
# checklist: the Makefile used to duplicate the literal).
DUCKDB_PATH = $(shell $(PY) -c "import yaml; print(yaml.safe_load(open('dbt_project/profiles.yml'))['trial_signal']['outputs']['duckdb']['path'])")
reset:
	@test -n "$(DUCKDB_PATH)" || { echo "ERROR: could not read the duckdb path from dbt_project/profiles.yml"; exit 1; }
	rm -f "$(DUCKDB_PATH)"

# push parsed parquet partitions to the S3 landing bucket. sync is
# content-aware: a byte-identical partition transfers 0 files on
# re-run; a re-parse rewrites the file and IS re-uploaded. Uploads are
# pinned to the bridge's exact artifact name (same class of shield as
# dbt's read glob): stray files in data/parsed/ — e.g. the "name N.ext"
# conflict copies a file-provider layer left during same-day overwrites
# (2026-08-16) — never reach the bucket, where a FORCE COPY of that
# partition would load them as duplicate rows.
s3-sync:
	@if [ -z "$$AWS_PROFILE" ]; then \
		echo "ERROR: AWS_PROFILE not set. Load it first: set -a; source .env; set +a"; \
		exit 1; \
	fi
	aws s3 sync data/parsed/ s3://$(S3_BUCKET)/$(S3_PREFIX)/ --exclude "*" --include "*/trials.parquet"

# COPY INTO RAW.TRIALS from the external stage (dbt macro
# load_raw_trials). Idempotent per partition (R2): delete the
# partition's rows, then COPY its files with FORCE — a same-partition
# re-run lands identical state. Default = latest local partition;
# DATE=YYYY-MM-DD picks one; ALL=1 re-loads every local partition
# (post-recreate path). preflight + pinned connection facts live in
# the script itself, so a direct invocation behaves identically.
load-snowflake:
	DBT='$(DBT)' DATE='$(DATE)' ALL='$(ALL)' scripts/load_snowflake.sh

# same dbt project on the snowflake target. Change detection and the
# RAG documents mart are duckdb-only this phase (DECISIONS.md):
# stg_trials_current+ excludes that whole subtree — the view itself
# (whose only consumers are the snapshot and doc mart; phase-7
# checklist ruling), the snapshot and its descendants, and the doc
# mart + its tests — plus the day-0 seeds. The circuit breaker is
# excluded too: it guards the duckdb-only snapshot, and on snowflake a
# thin partition usually means "not loaded yet" (R2 loads latest by
# default), not "ingest collapsed" — it would alarm on the wrong cause.
dbt-snowflake:
	$(snowflake_preflight)
	$(SNOWFLAKE_CONN) $(DBT) build $(DBT_SNOWFLAKE_FLAGS) --exclude stg_trials_current+ resource_type:seed assert_latest_partition_not_collapsed

# cross-target parity: staging row count + completeness mart must be
# value-identical on duckdb and snowflake; non-zero exit on mismatch.
verify-parity:
	DBT=$(DBT) PY=$(PY) scripts/verify_parity.sh

# build/refresh the Chroma vector store from mart_trial_documents.
# Incremental by content_hash: a re-run with no mart changes embeds 0
# documents. FULL=1 drops the collection and re-embeds everything.
rag-build:
	$(PY) -m rag.embed_and_store $(if $(FULL),--full,)

# ask a question over the store: make ask Q="why was NCTxxx withdrawn?"
# Optional: STATUS=WITHDRAWN PHASE=PHASE2 K=8. Needs ANTHROPIC_API_KEY
# in the environment (never passed as an argument or echoed).
# single-quoted interpolations so shell metacharacters in the values
# stay inert (review ruling S3); a literal ' in Q still breaks quoting —
# call rag.query_llm directly for questions containing apostrophes
ask:
	@if [ -z "$(Q)" ]; then echo "usage: make ask Q=\"your question\""; exit 2; fi
	$(PY) -m rag.query_llm '$(Q)' $(if $(STATUS),--status '$(STATUS)',) $(if $(PHASE),--phase '$(PHASE)',) $(if $(K),--k '$(K)',)

# golden-question eval. RETRIEVAL_ONLY=1 runs just the free deterministic
# half (no API calls).
eval:
	$(PY) -m rag.eval.run_eval $(if $(RETRIEVAL_ONLY),--retrieval-only,)

lint:
	$(VENV)/bin/pre-commit run --all-files
