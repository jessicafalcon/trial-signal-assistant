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
- [x] **4 Cloud** — Terraform S3 + Snowflake objects; COPY INTO.
      Exit: `make dbt-snowflake` green (dbt build on the snowflake
      target; snapshot subtree + seeds excluded, role/warehouse pinned
      by the target) — verified 2026-08-15 (17/17 PASS; staging row
      count and completeness-mart percentages identical to duckdb;
      s3-sync and COPY INTO idempotent for byte-identical files;
      terraform plan converged to "No changes"). Snapshot machinery
      deliberately duckdb-only this phase (DECISIONS.md 2026-08-15).
- [x] **5 RAG** — per-field embeddings + Chroma metadata filtering;
      cited Claude answers. The four F8 input-surface requirements
      settled (DECISIONS.md 2026-08-15): embedder reads
      mart_trial_documents; change key = content_hash (md5 of
      doc_text); arrays flatten with '; '; the seeds-import-parsers
      comment corrected. F11 RAW.TRIALS migration executed via
      scripts/recreate_raw_trials.sh.
      Exit: 10-question golden eval green — verified 2026-08-15
      (retrieval hit-rate 1.00 ≥ 0.8, citation correctness 1.00 ≥ 0.7;
      second make rag-build embeds 0 documents; suite 60/60, make dbt
      66/66, make dbt-snowflake 17/17 post-migration, lint green).
- [ ] **6 Orchestration** — Astro Airflow DAG end-to-end, idempotent.
      Also owns (2026-08-15 rulings): snapshot hard-delete policy AND
      Snowflake RAW.TRIALS reset mechanics, decided together with
      invalidate_hard_deletes (see DECISIONS.md 2026-08-14 deferral);
      an on-demand cross-target parity script.
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
- [ ] CI: SHA-pin ALL mutable action tags at flip time (currently 8
      checkout/setup-python instances plus hashicorp/setup-terraform@v3)
      and set persist-credentials: false on the secrets job.
- [ ] Doc-blocks refactor (accepted residual from the phase 3 review,
      ruling 2026-08-14): stg_trials_current's schema.yml repeats 13
      column descriptions verbatim from stg_clinical_trials — move shared
      descriptions to dbt doc blocks; also the Makefile hardcodes the
      DuckDB path that profiles.yml declares.
- [ ] Single-source the bucket name/prefix: Makefile S3_BUCKET/S3_PREFIX
      duplicate terraform's defaults and nothing consumes terraform
      output (2026-08-15 ruling F10).
- [ ] S3: add a noncurrent-version expiration lifecycle rule —
      versioning is on with no expiry, so rewritten partitions retain
      old versions forever (cost; 2026-08-15 ruling F14 residual).
- [ ] .terraform.lock.hcl carries darwin-only h1 hashes; record
      multi-platform hashes (terraform providers lock -platform=...)
      before the flip (2026-08-15 review note).
- [ ] stg_trials_current builds on the snowflake target though its only
      consumer (the snapshot) is duckdb-only — scope the exclusion or
      accept (2026-08-15 review note).
- [ ] Deferred tests from the phase-4 round (ruling F16): completeness
      mart bounds singular test; dual-target source-resolution parse
      test.
- [ ] Phase matching in the RAG CLI is exact-string only (PHASE2 does
      not match PHASE1/PHASE2) — consider Chroma $in / substring
      matching over decomposed phase values (phase-5 ruling C4:
      documented in --help now, richer matching deferred here).
- [x] .env.example lacks SNOWFLAKE_SCHEMA, which profiles.yml reads
      (defaults to 'public'); add it when Snowflake activates in phase 4,
      plus a make dbt-snowflake preflight failing fast on empty
      SNOWFLAKE_* vars (empty env_var() defaults mask missing creds).
      Done 2026-08-15: both landed with phase 4 (preflight covers
      account/user/password; the make targets pin the non-secret vars).
