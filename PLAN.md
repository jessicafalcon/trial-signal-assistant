# PLAN

Phase / goal / exit criterion. Details and rationale live in DECISIONS.md.

- [x] **0 Foundation** — scaffold, tooling, CI skeleton.
      Exit: `make setup` and `make lint` green; first commit pushed.
- [x] **1 Ingestion** — fixtures + tested parser; corpus parses clean.
      Exit: `make test` green in CI; full pulled corpus parses clean —
      verified ad-hoc 2026-08-14 (1,738 parsed, 0 warnings, 0 exceptions);
      the permanent check arrives as `make parse` in phase 2.
- [x] **2 Local warehouse** — parquet bridge, stg model, completeness
      model on DuckDB. (Planned "date macro" dropped: SPEC-02 rules that
      the Python parser owns all date handling — no SQL date parsing.)
      Exit: `dbt build --target duckdb` green locally (2026-08-14) and
      in CI (pending PR verification).
- [x] **3 Change detection** — snapshot (SCD2 on overall_status),
      synthetic labeled day-0 seed, mart_trial_status_changes.
      Exit: snapshot re-run on unchanged input yields zero new rows —
      verified 2026-08-14 (`make verify-idempotent`: 1742 rows before and
      after; mart shows exactly the 4 seeded transitions).
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
      revisit committed-hook inbound-PR surface before public flip;
      phase 7 pre-public audit checklist below cleared or re-accepted.

## Phase 7 pre-public audit checklist

Audit notes accepted-and-deferred during the 2026-08-14 pre-push review
rounds; clear or consciously re-accept each before the repo goes public:

- [ ] .env.example exception is filename-only at any depth with no content
      assertion — add a mechanical bare-keys check (every non-comment,
      non-blank line ends in "="); consider narrowing the gitignore
      negation to the root file.
- [ ] Floor asserts no minimum gitleaks version — have the script compare
      `gitleaks version` against CI's pin (8.30.1) and FAIL on mismatch
      (determinism: old binaries parse [[allowlists]]/condition
      differently).
- [ ] .gitleaks.toml is self-governing — a PR widening the allowlist
      disables the check for its own diff; consider CODEOWNERS or a CI
      guard on .gitleaks.toml/.gitignore changes.
- [ ] CI: SHA-pin actions/checkout + actions/setup-python (mutable tags;
      now five checkout/setup instances after the phase 2 dbt job) and
      set persist-credentials: false on the secrets job.
- [ ] Doc-blocks refactor (accepted residual from the phase 3 review,
      ruling 2026-08-14): stg_trials_current's schema.yml repeats 13
      column descriptions verbatim from stg_clinical_trials — move shared
      descriptions to dbt doc blocks; also the Makefile hardcodes the
      DuckDB path that profiles.yml declares.
- [ ] .env.example lacks SNOWFLAKE_SCHEMA, which profiles.yml reads
      (defaults to 'public'); add it when Snowflake activates in phase 4,
      plus a make dbt-snowflake preflight failing fast on empty
      SNOWFLAKE_* vars (empty env_var() defaults mask missing creds).
