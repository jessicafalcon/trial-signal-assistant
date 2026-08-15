# SPEC-02 — dbt staging layer on DuckDB

> Agent-loop spec. Read this file and CLAUDE.md fully before writing code.
> The definition of done is the DONE COMMAND below — nothing else.

## Goal

Stand up the dbt layer on the DuckDB target: a Parquet bridge from the
tested Python parser, a declared source, `stg_clinical_trials`, and a
field-completeness model — all schema-contracted and tested, green
locally and in CI.

## Context (verified — do not re-derive)

- Parsing rules live ONLY in Python (`ingest/fetch_clinical_trials.py`,
  15 passing tests). dbt never re-parses raw JSON; it models the
  parser's output. This is the single-owner rule — do not duplicate
  any parsing logic in SQL.
- TrialRecord fields (the parser's output, the bridge schema):
  nct_id, brief_title, overall_status, phase (joined string or null),
  sponsor_name, conditions (list), interventions (list of strings),
  start_date_raw, start_date (ISO string or null),
  date_precision ("day" | "month" | null), why_stopped (string or null),
  has_results (bool).
- Raw data: data/raw/ingest_date=2026-08-14/ (1,738 studies, parses
  clean end to end).
- dbt profiles.yml already has targets `duckdb` (default) and
  `snowflake`. Everything in this spec runs on `duckdb` only.

## Deliverables

1. `ingest/parse_to_parquet.py` + `make parse`:
   reads data/raw/ingest_date=<DATE>/, runs the EXISTING parser
   (import it — do not modify it), writes
   data/parsed/ingest_date=<DATE>/trials.parquet with one column per
   TrialRecord field plus `ingest_date`. List fields (conditions,
   interventions) serialize as Parquet lists. Same idempotency rule as
   ingest: overwrite own partition only. DATE defaults to the latest
   partition present in data/raw/.
2. `dbt_project/models/staging/sources.yml`: declare the parsed Parquet
   as a source (dbt-duckdb external location, glob over ingest_date
   partitions).
3. `dbt_project/models/staging/stg_clinical_trials.sql`, materialized
   as a VIEW: selects from the source, renames nothing (names are
   already clean), types are explicit, adds nothing computed. Staging
   is a typed pass-through, not a transformation layer.
4. `dbt_project/models/staging/schema.yml` written BEFORE the model SQL
   (engineering contract): every column with description + tests —
   unique + not_null on nct_id; not_null on overall_status, has_results,
   ingest_date; accepted_values on date_precision ('day','month' —
   configured to ignore nulls) and on overall_status (enumerate the
   distinct values actually present in the corpus; print the list in
   your summary for review).
5. `dbt_project/models/marts/mart_field_completeness.sql`, materialized
   as a TABLE, one row per ingest_date with: total_studies,
   pct_with_results, pct_withdrawn_or_terminated_with_why_stopped,
   pct_date_precision_day, pct_date_precision_month, pct_date_absent.
   Plus its schema.yml (not_null + unique on ingest_date).
6. `make dbt` wired for real: runs `dbt build --target duckdb` (deps,
   parse step NOT included — parse is a separate make target).
7. CI: new dbt job in .github/workflows/ci.yml that installs
   dbt-core + dbt-duckdb + pyarrow + requests, parses the FIXTURES
   (tests/fixtures/ studies) to a temp parquet via make parse
   FIXTURES=1 (add this mode to parse_to_parquet.py), then runs
   dbt build --target duckdb against it. CI must not need data/raw/.

## DONE COMMAND (the only definition of done)

    make parse && make dbt

All models build, all schema tests pass, zero errors zero warnings,
against the real 2026-08-14 partition. CI green is verified separately
on the PR.

## Constraints

- Touch only: ingest/parse_to_parquet.py, dbt_project/, Makefile,
  .github/workflows/ci.yml, tests/ (if adding parse-to-parquet tests).
- Do NOT modify: ingest/fetch_clinical_trials.py, tests/fixtures/,
  specs/SPEC-01*.
- New dependency: pyarrow is approved — add it to requirements.txt AND
  to CLAUDE.md's allowlist in the same commit. Nothing else without
  asking.
- Teaching rule applies: first use of source(), materializations,
  dbt tests, ref() each gets its 2-4 sentence explanation.
- SQL style per CLAUDE.md: keywords lowercase, one column per line.
- profiles.yml: the duckdb target stays fully credential-free; the
  snowflake target references env_var() only, with defaults that let
  dbt compile succeed without any secrets present (lint and CI must
  never need credentials).

## Out of scope (explicitly)

- Snapshots and mart_trial_status_changes (Phase 3 / SPEC-03).
- Snowflake target, COPY INTO, Terraform (Phase 4).
- Any date re-parsing in SQL — the parser owns dates.
- Embeddings, RAG (Phase 5).

## Loop protocol

1. Read CLAUDE.md, this spec, and the existing parser's public interface.
2. Write both schema.yml files first, then the SQL, then the bridge.
3. Run the DONE COMMAND after every change; iterate until green.
4. When green: run once more from a clean shell, update PLAN.md
   (phase 2 checkbox) and CLAUDE.md's Current status one-liner, commit
   ("phase 2: parquet bridge, staging + completeness on duckdb, dbt ci"),
   and summarize: files touched, the distinct overall_status values
   found, the completeness numbers from the mart, and decisions the
   spec didn't cover.
