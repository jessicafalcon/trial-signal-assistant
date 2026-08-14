# PLAN

Phase / goal / exit criterion. Details and rationale live in DECISIONS.md.

- [x] **0 Foundation** — scaffold, tooling, CI skeleton.
      Exit: `make setup` and `make lint` green; first commit pushed.
- [x] **1 Ingestion** — fixtures + tested parser; corpus parses clean.
      Exit: `make test` green in CI; full pulled corpus parses clean —
      verified ad-hoc 2026-08-14 (1,738 parsed, 0 warnings, 0 exceptions);
      the permanent check arrives as `make parse` in phase 2.
- [ ] **2 Local warehouse** — stg model, date macro, completeness model
      on DuckDB.
      Exit: `dbt build --target duckdb` green locally and in CI.
- [ ] **3 Change detection** — snapshot (SCD2 on overall_status),
      synthetic labeled day-0 seed, mart_trial_status_changes.
      Exit: snapshot re-run on unchanged input yields zero new rows.
- [ ] **4 Cloud** — Terraform S3 + Snowflake objects; COPY INTO.
      Exit: `dbt build --target snowflake` green.
- [ ] **5 RAG** — per-field embeddings + Chroma metadata filtering;
      cited Claude answers.
      Exit: 10-question golden eval runs with reported scores.
- [ ] **6 Orchestration** — Astro Airflow DAG end-to-end, idempotent.
      Exit: full DAG run succeeds twice in a row with identical results;
      demo assets captured.
- [ ] **7 Packaging** — README with screenshots, DECISIONS.md complete,
      case-study framing.
      Exit: a stranger can follow the README from clone to answer;
      revisit committed-hook inbound-PR surface before public flip.
