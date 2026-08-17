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
- [x] **6 Orchestration** — Astro Airflow DAG end-to-end, idempotent.
      Also owned (2026-08-15 rulings, both landed): R1 snapshot hard
      deletes (live-only, circuit-breaker-guarded) and R2 RAW.TRIALS
      delete-by-partition + scoped COPY FORCE; make verify-parity.
      Exit: verified 2026-08-15 — two same-day triggers all-green
      (11/11 tasks); second run an end-to-end no-op (delete 1738 /
      reload 1738, snapshot fingerprint unchanged, rag_build embedded
      0, parity OK on both targets); snowflake build stays 17/17 (the
      circuit breaker is duckdb-only by ruling); make test 98 locally
      (CI's test job skips the DAG tests — no airflow there; the
      dag-verify job runs them under Airflow's constraints file), lint
      and secrets floor green. Demo assets: docs/demo_checklist.md,
      captured after merge (open phase-6 deliverable — see phase 7
      checklist).
- [ ] **7 Packaging** — README with screenshots, DECISIONS.md complete,
      case-study framing.
      Exit: a stranger can follow the README from clone to answer;
      revisit committed-hook inbound-PR surface before public flip;
      phase 7 pre-public audit checklist below cleared or re-accepted.

## Phase 7 pre-public audit checklist

Audit notes accepted-and-deferred during the 2026-08-14 pre-push review
rounds; clear or consciously re-accept each before the repo goes public:

- [x] .env.example exception is filename-only at any depth with no content
      assertion — add a mechanical bare-keys check (every non-comment,
      non-blank line ends in "="); consider narrowing the gitignore
      negation to the root file.
      Done 2026-08-15 (phase 7): floor check (f) — offenders reported by
      line number only; negation narrowed to !/.env.example. Probe:
      planted value caught, restored file clean.
- [x] Floor asserts no minimum gitleaks version — have the script compare
      `gitleaks version` against CI's pin (8.30.1) and FAIL on mismatch
      (determinism: old binaries parse [[allowlists]]/condition
      differently).
      Done 2026-08-15 (phase 7): check (d) fails on any version != the
      GITLEAKS_PIN literal. Probe: fake 8.18.0 binary caught.
- [x] .gitleaks.toml is self-governing — a PR widening the allowlist
      disables the check for its own diff; consider CODEOWNERS or a CI
      guard on .gitleaks.toml/.gitignore changes.
      Done 2026-08-15 (phase 7): CI guard chosen over CODEOWNERS (a
      sole-maintainer repo can't require code-owner review of its own
      PRs) — on PRs the secrets job reruns gitleaks with the BASE
      branch's config, so an allowlist widening can't mask its own
      diff. .gitignore needs no twin: floor (a)/(b)/(e) don't consult
      it. Probe: config-override behavior verified (4 findings without
      the allowlist, 0 with).
- [x] CI: SHA-pin ALL mutable action tags at flip time (currently 8
      checkout/setup-python instances plus hashicorp/setup-terraform@v3)
      and set persist-credentials: false on the secrets job.
      Done 2026-08-15 (phase 7): 11 instances pinned (6 checkout →
      v4.4.0 SHA, 4 setup-python → v5.6.0 SHA, setup-terraform →
      v3.1.2 SHA), persist-credentials: false on every checkout (not
      just the secrets job — no job pushes).
- [x] Doc-blocks refactor (accepted residual from the phase 3 review,
      ruling 2026-08-14): stg_trials_current's schema.yml repeats 13
      column descriptions verbatim from stg_clinical_trials — move shared
      descriptions to dbt doc blocks; also the Makefile hardcodes the
      DuckDB path that profiles.yml declares.
      Done 2026-08-15 (phase 7): 13 shared columns in staging/_docs.md,
      referenced from both models; make reset reads the duckdb path
      from profiles.yml (pyyaml, already pinned).
- [x] Single-source the bucket name/prefix: Makefile S3_BUCKET/S3_PREFIX
      duplicate terraform's defaults and nothing consumes terraform
      output (2026-08-15 ruling F10).
      Resolved 2026-08-15 (phase 7) as sync-enforcement, not
      single-sourcing: the DAG container running make s3-sync has no
      terraform binary, so `terraform output` can't feed it; a pytest
      pins Makefile values == terraform defaults instead (DECISIONS.md
      phase-7 entry).
- [ ] S3: add a noncurrent-version expiration lifecycle rule —
      versioning is on with no expiry, so rewritten partitions retain
      old versions forever. URGENCY UP since phase 6: the daily DAG
      rewrites the same-day key on every same-day re-run (re-fetches
      are not byte-identical), so noncurrent versions now accrue per
      run, not per re-parse (cost; 2026-08-15 ruling F14 residual).
      Code landed 2026-08-15 (phase 7): 30-day noncurrent expiry +
      7-day multipart abort, terraform validate green. OPEN: the apply
      is a human gate (SPEC-07).
- [x] Phase-6 demo capture is an open IOU: docs/demo_checklist.md must
      be executed (screenshots + credit-burn number) before the
      phase-7 README case-study section can be written.
      Done 2026-08-15 pre-phase-7: 11 assets + INVENTORY.md in
      docs/assets/ (leak-inspected, exif-stripped); credit figure $2.25.
- [x] .terraform.lock.hcl carries darwin-only h1 hashes; record
      multi-platform hashes (terraform providers lock -platform=...)
      before the flip (2026-08-15 review note).
      Done 2026-08-15 (phase 7): h1 recorded for darwin_arm64/amd64 +
      linux_amd64/arm64.
- [x] stg_trials_current builds on the snowflake target though its only
      consumer (the snapshot) is duckdb-only — scope the exclusion or
      accept (2026-08-15 review note).
      Done 2026-08-15 (phase 7): scoped — dbt-snowflake now excludes
      stg_trials_current+ (covers the snapshot and doc-mart subtrees it
      carried); node diff verified to drop exactly the view + its 5
      tests. Snowflake build is 12 nodes from here on (17 before).
      (Superseded 2026-08-17: the external-review ruling reversed the
      scoping — change detection runs on snowflake; only
      mart_trial_documents, seeds, and the build-time snapshot stay
      excluded. DECISIONS.md change-detection entry.)
- [x] Deferred tests from the phase-4 round (ruling F16): completeness
      mart bounds singular test; dual-target source-resolution parse
      test.
      Done 2026-08-15 (phase 7): assert_mart_field_completeness_bounds
      (both targets) + test_source_resolves_per_target (dbt parse per
      target, manifest-asserted; credential-free). Suite 98 → 101.
- [x] Phase matching in the RAG CLI is exact-string only (PHASE2 does
      not match PHASE1/PHASE2) — consider Chroma $in / substring
      matching over decomposed phase values (phase-5 ruling C4:
      documented in --help now, richer matching deferred here).
      Re-accepted 2026-08-15 (phase 7): stays exact-string — documented
      in --help and the README production-notes section; richer
      matching goes to the post-public backlog, not this repo's demo
      scope.
Items SPEC-07 lists that this checklist lacked (added 2026-08-15 per the
spec's "report and do it" rule):

- [x] Whitespace-only cloud creds treated as present (phase-6 documented
      residual). Done 2026-08-15 (phase 7): the DAG gate strips before
      testing; whitespace-only now skips cleanly (test added).
- [x] MIT LICENSE file. Done 2026-08-15 (phase 7) — copyright holder is
      the GitHub handle; swap in a legal name at curation if preferred.
- [x] S3 versioning cost note — landed in the README cost-posture
      paragraph (30-day noncurrent expiry, why versions accrue per run).
- [x] CI-skip wording — tightened in the README rewrite: the test job
      runs the suite without airflow (DAG tests skip there); the
      dag-verify job installs airflow under its constraints and runs
      them; no cloud or API is ever touched in CI.
- [x] Committed-hook inbound-PR surface review — ruled 2026-08-15
      (option b): hook wiring moved to gitignored settings.local.json,
      script stays committed, re-enable block + conftest.py caveat in
      CLAUDE.md; DECISIONS.md entry.
- [x] Author-email posture line — history verified 2026-08-15: author
      and committer emails are exclusively the GitHub noreply address
      (102609780+jessicafalcon@users.noreply.github.com) and
      noreply@github.com; posture line recorded in the DECISIONS.md
      phase-7 entry.

- [x] .env.example lacks SNOWFLAKE_SCHEMA, which profiles.yml reads
      (defaults to 'public'); add it when Snowflake activates in phase 4,
      plus a make dbt-snowflake preflight failing fast on empty
      SNOWFLAKE_* vars (empty env_var() defaults mask missing creds).
      Done 2026-08-15: both landed with phase 4 (preflight covers
      account/user/password; the make targets pin the non-secret vars).
