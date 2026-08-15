# SPEC-03 — Change detection: snapshot, synthetic day-0, status-changes mart

> Agent-loop spec. Read this file, CLAUDE.md, and the grain ruling in
> DECISIONS.md before writing code. The DONE COMMAND is the only
> definition of done.

## Goal

Detect trial status changes over time: fix the staging grain per the
recorded ruling, snapshot `overall_status` (SCD2, check strategy) from
the latest partition, seed a labeled synthetic day-0 so the mechanism
is demonstrable now, and build `mart_trial_status_changes`. Prove
idempotency: re-running against unchanged data adds zero rows.

## Context (verified — do not re-derive)

- Staging grain ruling (DECISIONS.md): grain is (nct_id, ingest_date);
  staging keeps ALL partitions (the completeness mart is a time series);
  the SNAPSHOT alone reads only the latest partition.
- Real status enum + counts (2026-08-14 corpus): COMPLETED 1033,
  RECRUITING 184, UNKNOWN 169, TERMINATED 118, ACTIVE_NOT_RECRUITING 91,
  NOT_YET_RECRUITING 68, WITHDRAWN 54, ENROLLING_BY_INVITATION 17,
  AVAILABLE 2, NO_LONGER_AVAILABLE 1, SUSPENDED 1.
- dbt snapshots detect changes BETWEEN runs; two runs against two
  states produce the transitions.

## Deliverables

1. Grain fix: replace the bare `unique` test on stg_clinical_trials
   nct_id with a custom singular test (SQL file in dbt_project/tests/)
   asserting uniqueness of (nct_id, ingest_date) via group-by/having.
   No new packages (no dbt-utils). schema.yml description updated to
   state the grain.
2. `models/staging/stg_trials_current.sql` (view): staging filtered to
   the latest ingest_date — the snapshot's sole input surface. One
   column added: `snapshot_source` = 'live'. schema.yml with tests
   (unique + not_null nct_id — bare nct_id IS unique at this grain).
3. Seed `seeds/seed_synthetic_day0.csv` + seed config: exactly 4 real
   nct_ids from the corpus with lifecycle-plausible PREDECESSOR
   statuses (pick real trials currently in the successor state):
   ACTIVE_NOT_RECRUITING trial seeded as RECRUITING; RECRUITING trial
   seeded as NOT_YET_RECRUITING; TERMINATED trial seeded as RECRUITING;
   COMPLETED trial seeded as ACTIVE_NOT_RECRUITING. Columns: nct_id,
   overall_status, snapshot_source = 'synthetic_day0'. A comment header
   is impossible in dbt seed CSVs, so labeling lives in: the column,
   the seed schema.yml description ("synthetic demonstration state,
   not registry data"), and a DECISIONS.md entry.
4. Snapshot `snapshots/snap_trial_status.sql`: strategy='check',
   unique_key='nct_id', check_cols=['overall_status']. Its SELECT
   switches on var('snapshot_source', 'live'): 'seed' → the seed
   (only nct_id, overall_status, snapshot_source); 'live' →
   stg_trials_current (same three columns). No other var values;
   unknown value must fail the run loudly.
5. `models/marts/mart_trial_status_changes.sql` (table) + schema.yml:
   one row per detected transition, reading the snapshot's SCD2
   columns. Columns: nct_id, prior_status, new_status,
   changed_detected_at (dbt_valid_from of the new row),
   prior_source, new_source (so synthetic-origin transitions are
   visibly labeled in the mart itself). Tests: not_null on all,
   accepted_values on both status columns (the 11-value enum).
6. Makefile: `make snapshot-day0` (dbt seed + dbt snapshot with
   --vars snapshot_source: seed), `make snapshot` (dbt snapshot, live
   default). `make dbt` unchanged (build excludes snapshots by
   default behavior — verify and state which in the summary).
7. CI: the dbt job additionally runs the full sequence against
   fixtures (seed → snapshot day0 → snapshot live → build) proving
   the machinery end to end. Fixture-mode seed: the same 4 nct_ids
   only if present in fixtures, otherwise a fixture-scoped seed
   variant — choose, justify in the summary.
8. README: a short "Change detection" section — how the snapshot
   works, what the synthetic day-0 is, explicit disclosure that the
   four initial transitions are seeded demonstrations and all
   subsequent ones are real.

## DONE COMMAND (the only definition of done)

    make snapshot-day0 && make snapshot && make dbt && make verify-idempotent

where `make verify-idempotent` (new, part of deliverable 6) re-runs
`dbt snapshot` (live) and asserts via a query that the snapshot row
count did not change, exiting non-zero if it did. All green from a
clean state (delete the duckdb file first, document that in the
target or a make reset).

## Expected result (assert in the summary)

mart_trial_status_changes contains EXACTLY 4 rows — the four seeded
transitions, each prior_source='synthetic_day0', new_source='live' —
and the idempotency re-run adds zero snapshot rows.

## Constraints

- Touch only: dbt_project/, Makefile, .github/workflows/ci.yml,
  README.md, DECISIONS.md, PLAN.md.
- Do NOT touch: ingest/, tests/ (pytest), tests/fixtures/, specs/
  SPEC-01/SPEC-02, scripts/.
- No new dependencies of any kind.
- Teaching rule: seeds, SCD2 columns, vars, snapshot strategies each
  get their explanation at first use.
- The seed must never be mistakable for real registry state: the
  snapshot_source column travels through snapshot into the mart.

## Out of scope

- Snowflake, Terraform, COPY INTO (Phase 4). Embeddings/RAG (Phase 5).
- Airflow wiring of the snapshot (Phase 6).
- Any second real ingest (real transitions accrue naturally later).

## Loop protocol

1. Read the grain ruling, then write all schema.yml/test files first.
2. Implement in deliverable order; DONE COMMAND after every change.
3. When green: clean-state rerun, update PLAN.md phase 3 checkbox +
   CLAUDE.md status line, commit ("phase 3: snapshot change detection,
   synthetic day-0, status-changes mart"), summarize: the 4 mart rows
   verbatim, idempotency proof output, which nct_ids were seeded and
   why, decisions the spec didn't cover.
