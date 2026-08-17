# Post-review backlog

Parked, not forgotten. Two sources: (1) residuals from the final
scoped security pass over the phase-7 unpushed delta (2026-08-16;
0 secret / 0 critical — loop-control ruling ended the review-of-review
regress, DECISIONS.md pointer entry), and (2) product items deferred
to post-public by earlier rulings.

## Security residuals (final scoped pass, 2026-08-16)

- **B1 (should-fix): pin the two invariants the --skip-gitleaks flag
  rests on.** Extend tests/test_secrets_floor.py: (i) the
  .pre-commit-config.yaml secrets-audit hook must keep
  `pass_filenames: false` (if it ever flipped, a repo-root file named
  `--skip-gitleaks` would reach argv and mute check (d) locally);
  (ii) ci.yml's PRIMARY floor step must carry no `--skip` argument (a
  one-token edit would leave a green-looking secrets job with
  gitleaks off).
- **B2 (note): the self-governance guards are PR-only and branch
  protection lands at flip step 6 — after the phase-7 push.** The
  window is documented; when executing docs/public_flip_checklist.md,
  enable protection immediately with (not after) the merge.
- **B3 (note): the two PR guards are not independent.** The
  base-script guard skips check (d) by design (pin-bump deadlock), so
  the base-config step alone carries the gitleaks dimension on PRs;
  only the step-name assertion in test_secrets_floor.py protects its
  presence.
- **B4 (note): the S3 lifecycle rule is committed but unapplied**
  until flip checklist step 2 — main describes a control the bucket
  does not yet have; CI (fmt/validate only) will not surface the
  drift.

Informational, already documented elsewhere (no action): check (f) is
index-only/shape-based (DECISIONS residuals entry); the conftest.py
execution surface on inbound branches is human-mitigated only
(CLAUDE.md); LICENSE/DECISIONS carry the GitHub noreply identity
already on every commit.

## Product items (post-public, earlier rulings)

- Richer RAG phase matching: decomposed phase values + Chroma `$in`
  instead of exact-string (phase-5 ruling C4; README production
  notes).
- Retrieval quality: hybrid search / reranking for rare drug tokens;
  sponsor names semantically searchable, not just filterable
  (phase-5 golden-set findings; README production notes).
- Delisted-trials mart: R1's closed rows (dbt_valid_to set, no
  successor) are write-only today — no mart, README, or RAG document
  surfaces them (R1 scope cut, DECISIONS.md).

## External-review items (2026-08-16 dispositions, documented answers)

Ruled DOCUMENT in the pre-flip review round (DECISIONS.md external-
review entry); each has its unprompted answer in README production
notes and graduates here if the project outgrows demo scope:

- Snowpipe off S3 event notifications as the at-volume load path;
  keep the partition-scoped delete+reload as backfill/replay.
- Data-aware orchestration: Airflow assets, Cosmos for dbt-aware task
  mapping, deferrable S3 sensors, managed deployment (Astro/MWAA).
- Governed retrieval: Cortex Search over mart_trial_documents,
  replacing Chroma + the local embedding path.
- Scheduled cross-target parity job with scoped read-only creds
  (never creds in CI); alerting/SLA path on the deployed DAG;
  terraform remote backend + locking; incremental ingest filtered on
  the registry's last-update date.
