# Trial & Safety Signal Assistant

A data + GenAI pipeline over public clinical trial data (atopic dermatitis)
from ClinicalTrials.gov: dbt models on a dual warehouse (DuckDB locally and
in CI, Snowflake for demo), dbt snapshots tracking trial status changes over
time, and a RAG layer that answers natural-language questions ("why was this
trial withdrawn?") with cited Claude API answers. Deterministic SQL/Python in
the middle; the LLM only writes prose over retrieved context.

## Architecture

```
ClinicalTrials.gov API v2
        │  (ingest/fetch_clinical_trials.py — tested parser)
        ▼
S3 raw landing (JSON, partitioned by ingest date)   [Terraform, eu-west-3]
        │
        ├──► DuckDB  (local dev + CI target)
        └──► Snowflake (demo target, COPY INTO via external stage)
        │
        ▼
dbt: staging ──► snapshots (SCD2 on overall_status) ──► marts
        │
        ▼
Embeddings (sentence-transformers, per-field docs) ──► Chroma (+ metadata)
        │
        ▼
RAG retrieval ──► Claude API ──► grounded answer with NCT citations
```

Control plane: Airflow DAG (Astro, daily) · GitHub Actions CI · Terraform.

## Setup

Prerequisites: Python 3.11+, and [gitleaks](https://github.com/gitleaks/gitleaks)
(`brew install gitleaks`) for the secrets audit (`scripts/secrets_audit.sh`),
run by a local pre-push hook and in CI on pushes to main and on pull requests.

    make setup   # venv, dependencies, pre-commit hooks
    make test    # parser suite (no network)

## Change detection

`dbt snapshot` keeps SCD2 history of each trial's `overall_status`: every
run compares the current staging state (latest ingest partition only)
against what it saw before, and writes a new dated row only when a status
changed. `mart_trial_status_changes` pairs consecutive history rows into
one row per transition. Re-running against unchanged data adds zero rows
(`make verify-idempotent` proves it).

Because real status changes take months to accrue, `make snapshot-day0`
seeds a synthetic "day 0": four real trial ids with plausible predecessor
statuses, labeled `snapshot_source='synthetic_day0'`. The four initial
transitions in the mart are therefore seeded demonstrations — the label
travels into the mart's `prior_source` column — and every transition
after them is real registry change, labeled `live` on both sides.

Status: phase 3 complete — see PLAN.md.
