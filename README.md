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
data/raw JSON ──► parser bridge ──► data/parsed parquet (ingest_date partitions)
        │
        ├──► DuckDB (local dev + CI target — reads the parquet directly)
        └──► aws s3 sync ──► S3 parsed/ landing [Terraform, eu-west-3]
                                   └──► COPY INTO Snowflake RAW.TRIALS
                                        (external stage; demo target)
        │
        ▼
dbt: staging ──► snapshots (SCD2 on overall_status; duckdb only) ──► marts
        │
        ▼
Embeddings (sentence-transformers, per-field docs) ──► Chroma (+ metadata)
        │
        ▼
RAG retrieval ──► Claude API ──► grounded answer with NCT citations
```

Control plane: Airflow DAG (Astro, daily) · GitHub Actions CI · Terraform.

## Setup

Prerequisites: Python 3.11 for the venv — the reference version, matching
CI exactly (3.12/3.13 acceptable; 3.14 unsupported: `make dag-verify`
installs apache-airflow under Airflow's published constraints, which
exist for 3.11–3.13 only, and the target fails loudly on anything
else), [gitleaks](https://github.com/gitleaks/gitleaks)
(`brew install gitleaks`) for the secrets audit (`scripts/secrets_audit.sh`),
run by a local pre-push hook and in CI on pushes to main and on pull requests.
For the cloud target only: the aws CLI (`brew install awscli`) and
[terraform](https://developer.hashicorp.com/terraform)
(`brew install hashicorp/tap/terraform`). `make setup` warns when any of
the three is missing.

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

## Cloud target (S3 + Snowflake)

The same dbt project runs on Snowflake to prove the models are
warehouse-portable; DuckDB stays the default local/CI target and needs
none of this. One-time provisioning (creates the S3 landing bucket, the
Snowflake database/schemas/warehouse/role, and the storage-integration
trust handshake) is a single converging `terraform apply` — sequence,
required env vars, and IAM caveats in [terraform/README.md](terraform/README.md).

Then the load + build flow:

    make s3-sync         # parsed parquet → s3://<bucket>/parsed/ (0 files re-sent on re-run)
    make load-snowflake  # per-partition: delete that partition's rows, COPY its files with FORCE
    make dbt-snowflake   # dbt build --target snowflake (staging + completeness mart + tests)

`aws s3 sync` skips byte-identical files. The Snowflake load is
idempotent per partition (R2, phase 6): each run deletes the target
partition's rows and re-COPYs its stage files with `FORCE = TRUE`, so
a same-partition re-run — unchanged file or re-parse — converges to
the file's current contents instead of appending duplicates. Default
is the latest local partition; `DATE=YYYY-MM-DD` picks one, `ALL=1`
loads every local partition. If `verify-parity` reports Snowflake
missing a partition (e.g. a day when the DAG's cloud tasks were
skipped), the recovery is `make load-snowflake ALL=1`.
Credentials live only in `.env` (see `.env.example`); the make targets
pin role/warehouse/database/schema to the terraform-created objects
(`TRANSFORMER` / `TRIAL_SIGNAL_WH` / `TRIAL_SIGNAL` / `ANALYTICS`).

Cost posture: X-Small warehouse, 60-second auto-suspend, created
suspended — a full load + build run fits comfortably in trial credits.
Snapshot machinery (change detection) and the RAG documents mart run on
DuckDB only this phase; `make dbt-snowflake` excludes them. Snowflake is
never exercised in CI — CI only checks `terraform fmt`/`validate` with
no credentials.

**Schema migration (RAW.TRIALS):** the table's DDL is a manual mirror of
the parser's parquet schema, and `create table if not exists` never
alters a live table. When `TrialRecord` gains a column, recreate and
re-load — the data is reproducible by design:

    make parse && make s3-sync                # rewrite + upload the parquet
    CONFIRM=1 scripts/recreate_raw_trials.sh  # drop + recreate from the updated DDL
    make load-snowflake ALL=1 && make dbt-snowflake

(`ALL=1` because the fresh table needs every local partition — the
default load is latest-partition-only since R2.)

## Ask questions (RAG)

`mart_trial_documents` turns each trial's free-text fields
(`brief_summary`, `detailed_description`, `why_stopped`) into one
document per field. `make rag-build` embeds them (pinned
sentence-transformers model) into a local Chroma store with the trial's
status/phase/sponsor as filterable metadata; re-runs re-embed only
documents whose `content_hash` changed (a no-change re-run embeds 0).
`make ask` retrieves the top-k documents for a question and has Claude
(temperature 0, pinned model) write an answer grounded ONLY in that
context, citing NCT ids — or refusing when the context is insufficient.

    make rag-build                       # build/refresh the vector store (FULL=1 rebuilds)
    make ask Q="why was the tezepelumab trial stopped?"
    make ask Q="which phase 2 trials met futility criteria?" STATUS=TERMINATED PHASE=PHASE2
    make eval                            # 10 golden questions, scored (RETRIEVAL_ONLY=1 = no API)

`make ask` needs `ANTHROPIC_API_KEY` in the environment and prints JSON:

    {
      "answer": "The tezepelumab monotherapy trial ... did not reach the
                 targeted efficacy level ... [NCT03809663].",
      "cited_nct_ids": ["NCT03809663"],
      "unverified_nct_ids": [],
      "retrieved_ids": ["NCT03809663:why_stopped", "..."],
      "model": "claude-sonnet-4-5-20250929"
    }

`cited_nct_ids` only ever contains ids that were actually retrieved for
this question; any other id the model mentions is reported under
`unverified_nct_ids` and never counts as a citation.

`make eval` scores retrieval hit-rate (deterministic, free) and citation
correctness (one API call per question) against
`rag/eval/golden_questions.yml`, failing below 0.8 / 0.7.

## Run it on a schedule (Airflow)

One daily DAG (`trial_safety_pipeline`) runs the whole pipeline, local
Docker only via the Astro CLI — Airflow never runs in CI:

    set -a; source .env; set +a   # cloud credentials for the containers (optional)
    cd airflow
    astro dev start      # builds the image, starts Airflow, prints the UI URL
    # UI: unpause trial_safety_pipeline, Trigger. astro dev stop when done.

Each task shells into the repo mount and calls its make target — make
is the tested interface; the DAG orchestrates, it never reimplements:

    ingest → parse → circuit_breaker
      → dbt_duckdb (live snapshot + full build) → verify_idempotent
      → rag_build ─┐
      → cloud: check_cloud_creds → s3_sync → load_snowflake → dbt_snowflake ─┤
                                                    cloud: verify_parity  ◄──┘

Local before cloud: a missed cloud load is recoverable any time
(`make load-snowflake ALL=1`), a missed snapshot day only by same-day
manual intervention — so a cloud outage must never block the snapshot.

- **circuit_breaker** — the snapshot invalidates hard deletes on live
  runs, so a collapsed ingest would read as mass delisting. The run
  fails if the latest partition holds under 80% of the prior one's
  rows (`circuit_breaker_min_ratio` var).
- **check_cloud_creds** skips the cloud tasks (reason in its log) when
  `SNOWFLAKE_*` / `AWS_PROFILE` are missing; the local path has already
  run by then (`verify_parity` inherits the skip via `all_success`).
  A skipped day leaves Snowflake one partition behind — recovery is
  `make load-snowflake ALL=1` (verify_parity's failure message says so).
- **Idempotent**: a same-day second trigger is an end-to-end no-op —
  same-partition overwrite, delete + `COPY FORCE` reload of that one
  Snowflake partition, snapshot fingerprint unchanged, `rag_build`
  embeds 0 (verified 2026-08-15, both triggers all-green).
- **Credentials are runtime-only and scoped**:
  `docker-compose.override.yml` passes exactly four env vars
  (`SNOWFLAKE_ACCOUNT/USER/PASSWORD`, `AWS_PROFILE`) from the shell
  that runs `astro dev start` — hence the `source .env` above — and
  mounts only `~/.aws/config` + `~/.aws/credentials`, read-only. The
  image carries none of it — build context is `airflow/` with `.env`
  dockerignored (verified: a bare `docker run ... env` shows no
  credential vars). Without the export, everything still starts and
  the cloud group skips.
- CI runs `make dag-verify` instead: DagBag import + structure tests,
  pure Python, with `apache-airflow` pinned in
  `airflow/requirements-dagtest.txt` and installed only by that target.
- `snapshot-day0` is not in the DAG on purpose — it is a one-time
  bootstrap; re-running it would corrupt the demo transitions.

Production notes (out of scope by design): deploying the DAG (Astro
cloud / MWAA), alerting/SLAs, and backfills. `catchup=False` — ingest
fetches "today", so backfilled runs would be meaningless. Known
circuit-breaker limits: the 0.8 ratio compares only the latest
partition to its immediate prior, so an 86% single-day truncation or a
multi-day slow drift passes; an empty latest partition also passes
(the snapshot then re-reads the prior day — see DECISIONS.md).

Status: phase 6 complete — see PLAN.md.
