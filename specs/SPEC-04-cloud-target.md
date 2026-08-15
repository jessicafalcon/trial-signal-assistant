# SPEC-04 — Cloud target: Terraform (S3 + Snowflake), load, dbt on Snowflake

> Agent-loop spec. Read this, CLAUDE.md, and DECISIONS.md grain/snapshot
> entries first. The DONE COMMAND is the only definition of done.
> Credentials exist ONLY as environment variables / AWS profile — never
> ask for them, never echo them, never write them to any file.

## Goal

Provision the cloud path with Terraform (S3 landing bucket + Snowflake
database/schemas/warehouse/role), load the parsed Parquet into Snowflake
via external stage + COPY INTO, and run the SAME dbt project green on
the snowflake target — proving the dual-target design end to end.

## Context (verified — do not re-derive)

- Snowflake trial: Standard edition, AWS, eu-west-3 (Paris). Account
  identifier + admin credentials are in the user's .env as the
  SNOWFLAKE_* vars from .env.example. AWS: profile "trial-signal"
  (AWS_PROFILE in .env), IAM user scoped to S3 only, region eu-west-3.
- Parsed data: data/parsed/ingest_date=2026-08-14/trials.parquet
  (1,738 rows). The duckdb target reads it as an external source; the
  snowflake target must read an equivalent loaded table.
- profiles.yml snowflake target already exists: env_var()-only, parse
  green with no secrets, connection failure without credentials is
  expected (SPEC-02 amendment).
- .gitignore already covers *.tfstate, *.tfstate.*, *.tfvars,
  *.tfvars.json, *.pem, *.p8, .env*.

## Deliverables

1. terraform/ (split files: providers.tf, s3.tf, snowflake.tf,
   variables.tf, outputs.tf):
   - Pinned provider versions (aws, snowflakedb/snowflake), pinned
     required_version for terraform. Local state (gitignored — verify
     and state so in the summary).
   - S3: one bucket (name from a variable with a sensible default,
     eu-west-3), block-public-access ON, default SSE encryption,
     versioning enabled.
   - Snowflake: database TRIAL_SIGNAL; schemas RAW and ANALYTICS;
     X-Small warehouse auto_suspend=60, auto_resume, initially
     suspended; role TRANSFORMER with least-privilege grants (usage on
     db/schemas/warehouse; create/select on RAW and ANALYTICS as
     needed by COPY INTO + dbt); grant TRANSFORMER to the admin user
     (from a variable). No new Snowflake users, no passwords in
     Terraform.
   - Storage integration for the S3 stage: snowflake_storage_integration
     + the matching AWS IAM role with Snowflake's external ID in its
     trust policy. This is inherently two-phase (the integration's
     STORAGE_AWS_IAM_USER_ARN / EXTERNAL_ID are known only after
     creation) — implement the standard two-apply flow, document the
     exact sequence in terraform/README.md, and make the second apply
     converge (plan shows no changes afterward).
   - External stage in RAW pointing at the bucket via the integration,
     FILE_FORMAT for Parquet.
2. Load path: scripts/load_snowflake.sh (or .py using only allowlisted
   deps) + Makefile targets:
   - make s3-sync — aws s3 sync of data/parsed/ to the bucket
     (aws CLI is a system prerequisite like gitleaks: document in
     README setup, make setup warns if absent).
   - make load-snowflake — COPY INTO RAW.TRIALS from the stage
     (MATCH_BY_COLUMN_NAME, Parquet), idempotent: re-running without
     new files loads 0 rows (COPY's default load history — state this
     in the summary with proof).
3. dbt dual-target source: the snowflake target's source resolves to
   RAW.TRIALS while duckdb keeps the external Parquet path. Implement
   with target-conditional jinja in sources.yml (or the cleanest
   equivalent — justify the mechanism chosen in the summary; the
   constraint from SPEC-02 stands: no env-var-into-SQL injection
   surface).
4. Cross-target compatibility: list columns (conditions,
   interventions) arrive as ARRAY/VARIANT in Snowflake vs DuckDB
   lists; timestamps and booleans may differ. Adjust staging SQL /
   schema tests ONLY where cross-target reality requires it, each
   divergence isolated in jinja target conditionals and listed in the
   summary. The completeness mart's percentages MUST be identical on
   both targets.
5. CI: add terraform fmt -check and terraform validate (no init
   against real backends beyond providers mirror; NO credentials in
   CI, no plan/apply in CI — state this in ci.yml comments). The
   existing duckdb dbt job is untouched. Snowflake is never exercised
   in CI.
6. Docs: README gains a Cloud target section (two-apply sequence,
   make s3-sync / load-snowflake / dbt-snowflake flow, cost posture:
   XS warehouse, 60s suspend, trial credits). PLAN.md phase 4
   checkbox; CLAUDE.md commands + status updated.

## DONE COMMAND (the only definition of done)

    make dbt-snowflake

green (build + tests) against the loaded RAW.TRIALS — AND the
verification block below, run and reported verbatim:

1. terraform plan → "No changes" (post-convergence idempotency)
2. make s3-sync twice → second run transfers 0 files
3. make load-snowflake twice → second run loads 0 rows
4. Row-count parity: staging count on snowflake == 1738 == duckdb
5. Completeness mart parity: identical percentages on both targets
6. make dbt (duckdb) still green — the dual-target promise holds

## Constraints

- Touch only: terraform/, scripts/, Makefile, dbt_project/,
  .github/workflows/ci.yml, README.md, CLAUDE.md, PLAN.md,
  DECISIONS.md, .env.example (SNOWFLAKE_SCHEMA addition, deferred
  from phase 2).
- NEVER print, log, or write credential values; terraform output must
  not expose secrets (mark sensitive where applicable).
- No new Python dependencies without asking; aws CLI + terraform are
  system prerequisites (README setup + make setup warnings).
- Snapshot machinery (snapshots, seeds, verify-idempotent) is NOT
  exercised on snowflake in this phase — document as a deliberate
  scope line in DECISIONS.md (demo runs on duckdb; snowflake proves
  the warehouse path). make dbt-snowflake must therefore exclude
  snapshot-dependent models if needed — state how in the summary.
- Teaching rule: storage integration/external stage, COPY INTO load
  semantics, terraform state, and target-conditional jinja each get
  their 2-4 sentence explanation at first use.

## Out of scope

- Airflow (Phase 6). RAG (Phase 5). Snowflake key-pair auth, Snowpipe,
  RBAC beyond TRANSFORMER (README "production notes" material).
- CI against Snowflake — permanently out, by policy.

## Loop protocol

1. Terraform first (fmt/validate locally), then STOP and hand me the
   exact apply commands to run MYSELF for the two-phase apply — the
   human runs terraform apply, not the loop. Wait for my confirmation
   that apply succeeded before continuing.
2. Then load path, then dbt source/compat work, iterating the DONE
   COMMAND.
3. When green: clean verification block, docs, commit ("phase 4:
   terraform cloud target, s3+copy load, dbt on snowflake"),
   summary per the deliverables' "state in the summary" items +
   uncovered decisions. Do not push.
