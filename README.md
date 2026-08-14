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

Status: phase 1 complete — see PLAN.md.
