# SPEC-06 — Orchestration: Airflow (Astro), operational guards, demo

> Agent-loop spec. Read this, CLAUDE.md, and the deferred phase-6 items
> in DECISIONS.md (snapshot hard deletes; Snowflake reset mechanics;
> parity script) first. The DONE COMMAND is the only definition of done.
> Airflow runs ONLY locally in Docker — never in CI.

## Goal

One daily DAG running the whole pipeline end to end — ingest → parse →
cloud load → dual dbt builds → snapshot → RAG reindex — idempotent at
every task, with the two deferred operational rulings implemented, and
the demo assets captured while everything is live.

## Context (verified — do not re-derive)

- User chose full Astro/docker-compose Airflow at project start.
  Docker Desktop + Astro CLI are installed (human-verified prereq).
- The repo already has dags/trial_safety_pipeline.py as a stub concept;
  everything real lives behind make targets, which are the tested
  interface — the DAG orchestrates make, it does not reimplement logic.
- Canonical local order: reset-free daily flow is parse → dbt run/test
  → snapshot (live) → build; snapshot-day0 is a one-time bootstrap,
  NEVER in the DAG.
- Deferred ruling 1 (phase-3 F9): invalidate_hard_deletes unset — a
  delisted trial reads as current forever. The day0-rerun interaction
  risk is void inside the DAG (day0 never runs there).
- Deferred ruling 2 (phase-4 F6): RAW.TRIALS is append-only; a re-parse
  of an existing partition re-loads and the grain test fails loudly;
  no delete/truncate path exists.
- Credentials exist in the user's .env / ~/.aws only. Astro containers
  need them at runtime for cloud + API tasks.

## Rulings implemented by this spec (write DECISIONS entries for both)

R1 — Hard deletes: enable invalidate_hard_deletes on the snapshot,
guarded by a circuit breaker: a singular dbt test (or pre-snapshot
check task) that FAILS the run if the latest partition's row count is
< 80% of the prior partition's — a collapsed ingest must never
mass-invalidate the snapshot. Threshold is a var; justify the default.

R2 — Snowflake load idempotency: before COPY, delete-by-partition
(delete from raw.trials where ingest_date = <partition being loaded>),
making make load-snowflake safely re-runnable for the same partition.
State the COPY FORCE implications you chose in the summary.

## Deliverables

1. Astro project in airflow/ (astro dev init there — NOT repo root):
   Dockerfile pinned to an Astro Runtime version, airflow/requirements
   mirroring only what tasks need in-container, and a
   docker-compose.override.yml mounting the repo at
   /usr/local/airflow/repo (read-write: data/ and the duckdb file live
   there) and passing the .env through (document that this is
   local-only; CI never sees it).
2. dags/trial_safety_pipeline.py rewritten as the real DAG (the file
   moves into airflow/dags/ if Astro requires; leave a pointer or
   relocate cleanly — state which): schedule daily, catchup=False,
   max_active_runs=1, retries with backoff on network tasks. Tasks,
   each a BashOperator cd-ing into the repo mount and calling make:
   ingest → parse → circuit_breaker (R1 check) → s3_sync →
   load_snowflake (R2 path) → dbt_snowflake → dbt_duckdb (canonical
   order incl. snapshot live) → verify_idempotent → rag_build →
   verify_parity. Cloud tasks in one TaskGroup so a no-credentials
   environment can still run the local path (trigger rule /
   skip-with-reason — justify the mechanism).
3. make verify-parity (the phase-4 deferred parity script): row count
   + completeness-mart JSON compare across targets, non-zero on
   mismatch — runnable standalone and as the DAG task.
4. DAG integrity tests runnable WITHOUT Docker (pytest: DagBag imports
   clean, task ids + dependencies match the documented order, no
   schedule surprises) — wired into the normal suite and CI (airflow
   package as a test dependency ONLY if needed; if so it needs
   approval — ask, with the version, before adding).
5. Idempotency of the daily run: second trigger on the same day must
   be a no-op end to end (same-partition overwrite, R2 delete+reload,
   snapshot 0 new rows, rag-build 0 embedded / 0 deleted). This is
   the core operational claim — prove it in the verification block.
6. Docs: README "Run it on a schedule" (astro dev start, trigger,
   what each task does, the circuit breaker's why), CLAUDE.md
   commands/repo map/status, PLAN phase 6, DECISIONS (R1, R2, Astro
   layout choice).
7. DEMO CAPTURE CHECKLIST (human executes; the loop produces the
   checklist file docs/demo_checklist.md and stops before capture):
   - Airflow graph view, one all-green run (the money shot)
   - Snowsight: TRIAL_SIGNAL schemas + RAW.TRIALS row count
   - Warehouse config showing auto_suspend=60 + Cost Management after
     a full run (credit burn number for the README)
   - Terminal: make ask Q1 full JSON output
   - Terminal: make eval summary table
   - Terraform plan "No changes" tail
   - (optional GIF: trigger → tasks lighting up green)

## DONE COMMAND (the only definition of done)

    make test && make dag-verify

where make dag-verify runs the DagBag/structure tests. PLUS the
in-Docker verification block, run once and reported verbatim:
1. astro dev start clean; DAG parses in the UI with no import errors
2. One triggered run: ALL tasks green (screenshot moment)
3. Same-day second trigger: end-to-end no-op per deliverable 5 —
   report each task's evidence line
4. make dbt-snowflake and make dbt (host side) still green after both
   runs; suite + lint + secrets floor green

## Human gates (STOP points)

1. Before first astro dev start: STOP, hand me the exact commands —
   I start Docker/Astro and trigger runs myself; you read results
   from my paste-backs and the mounted artifacts.
2. Demo capture is entirely mine, after the verification block.

## Constraints

- Touch only: airflow/, dags/, Makefile, scripts/, dbt_project/
  (R1/R2 only), tests/, docs/, README, CLAUDE.md, PLAN.md,
  DECISIONS.md, ci.yml (integrity tests only). CI gets NO Docker, NO
  Airflow runtime, NO credentials — integrity tests must be pure
  Python imports.
- No new deps without asking (airflow-as-test-dep needs explicit
  approval; in-container requirements are exempt but must be pinned
  and listed in the summary).
- Never bake credentials into the image, compose files, or DAG code —
  runtime env passthrough only; verify the built image layers carry
  no .env content (state how you verified).
- Teaching rule: DAG/task semantics, trigger rules, catchup,
  BashOperator-vs-provider-operators tradeoff, and Astro's project
  layout each get their explanation at first use.

## Out of scope

- Deploying Airflow anywhere (Astro cloud, MWAA) — README production
  notes. Alerting/SLAs. Backfills. Multi-day scheduling proof (one
  same-day idempotency proof suffices; real daily runs accrue on
  their own).

## Loop protocol

1. R1/R2 first (they're dbt/script-side and testable without Docker),
   then the Astro project, then the DAG, then integrity tests.
2. Human gate 1 before any Docker start; iterate on my paste-backs.
3. When the verification block is green: docs + checklist file, single
   phase-6 commit ("phase 6: airflow orchestration, operational
   guards, demo checklist"), summary (verification block verbatim,
   R1 threshold justification, R2 FORCE choice, in-container dep list,
   uncovered decisions). Do not push. Demo capture happens after
   merge, on main, by the human.
