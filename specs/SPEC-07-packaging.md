# SPEC-07 — Packaging: README, case study, pre-public audit, the flip

> Final phase. Mixed mode: mechanical checklist items are loop work;
> the README narrative and case study are DRAFT-then-human-curated —
> the human's edits are final. The public flip is a human action.

## Goal

Turn the repo into a portfolio artifact a stranger understands in
five minutes without cloning: what it is, why it's built this way,
proof it works — then close every deferred audit item and flip to
public with a clean, verified history.

## Context (verified — do not re-derive)

- All six build phases are merged; demo assets are captured in
  docs/assets/ (human-verified list in the summary's first section —
  read the directory, don't assume names).
- PLAN.md holds the accumulated "phase 7 pre-public audit" checklist
  and the phase-7 exit line items. That checklist IS deliverable 3.
- Repo is PRIVATE; branch protection unavailable until public
  (free tier). Naming is neutral by decision; the target-company
  framing lives ONLY in the case-study section.
- Communication style rules apply to the README with full force:
  result-first, plain English, no filler adjectives; show properties,
  don't claim them.

## Deliverables

1. README.md rewrite (DRAFT → STOP for curation → finalize):
   - Top: one-paragraph what/why, then the architecture diagram, then
     the money screenshot (Airflow all-green run) with a caption.
   - "Ask it a question": the Q1 make ask JSON verbatim, then the
     eval table, then two sentences on how citations are verified
     (intersection with retrieved set; refusal question).
   - "What it proves" — five short evidence blocks, each = claim +
     the command/artifact that proves it: dual-target parity (mart
     JSON identical), change detection (4 seeded transitions,
     idempotency fingerprint), cloud path (terraform plan "No
     changes", COPY 1738/1738), determinism (byte-identical answers,
     0-embedded re-run), operational safety (circuit breaker,
     no-creds skip, same-day no-op run).
   - Setup + run: prerequisites (python 3.11 ref, brew list), the
     canonical command order, the Airflow start with the source .env
     requirement, cost posture (XS/60s + the measured credit number).
   - "Production notes" — what changes at scale, in prose: Cortex
     Search vs local embeddings, key-pair auth, Snowpipe, RBAC beyond
     TRANSFORMER, alerting/SLAs, the breaker's declared blind spots,
     sponsor-search limitation, richer phase matching. Honest, short.
   - "How it was built": two paragraphs — spec-driven agent loops for
     deterministic work, human gates for judgment (pushes, applies,
     curation, audits); the two-layer security model; the audit-
     termination decision. This is a selling point, not a footnote.
   - Case study section (LAST; the tunable part): the enterprise
     assistant-pattern framing, the AD/immunology choice, the trial-
     status/cycle-time angle. Naming the target company is the human's
     call at curation — draft it with a placeholder.
   - Status line → "complete", link to DECISIONS.md and PLAN.md.
2. DECISIONS.md completeness pass: every "superseded by →" pointer
   present; every phase-N deferral resolved or explicitly parked with
   a reason; a short index at top by phase. No rewriting of entries.
3. Pre-public audit checklist — execute EVERY item accumulated in
   PLAN.md's phase-7 list. Known contents (verify against the file;
   the file wins): SHA-pin all mutable GitHub Action tags +
   persist-credentials: false; gitleaks version pin in the floor;
   .env.example content assertion; self-governing .gitleaks.toml
   guard (CODEOWNERS or CI check on config changes); doc-blocks
   refactor for repeated column descriptions; noncurrent-version
   expiration on the S3 bucket (terraform — hand me the apply);
   bucket single-sourcing from terraform output; lock file
   multi-platform hashes; stg_trials_current scoping on snowflake;
   two deferred tests; whitespace-creds .strip(); S3 versioning cost
   note; CI-skip wording; committed-hook inbound-PR surface review;
   author-email posture line; MIT LICENSE file. Anything the file
   lists that isn't here: do it too. Anything here the file lacks:
   report and do it.
4. Final full audit at the boundary — the second real one:
   scripts/secrets_audit.sh (floor, full history) + the
   security-reviewer judgment pass over the WHOLE tree with the
   question "anything here that must not be public?" — including
   docs/assets/ (screenshots can leak account identifiers, URLs,
   emails: inspect every image, list what each shows). Findings go
   to the human; the convergence rule from the pre-push audit applies
   (human ends it, notes get parked in a post-public backlog).
5. Repo hygiene for a public reader: topics/description text drafted
   for the GitHub repo settings; .github/ has no template debris;
   airflow/README is the 5-line pointer; no TODO/FIXME left in code
   without an issue reference (list them; the human decides).

## DONE COMMAND (the only definition of done)

    make test && make dag-verify && make dbt && bash scripts/secrets_audit.sh

green on main after everything merges — PLUS the human has: curated
the README, ruled the final audit, applied the terraform lifecycle
change, and executed the flip checklist below.

## Human gates (STOP points)

1. README curation: the loop drafts, STOPS, the human edits (case-
   study naming decided here), the human's version is final.
2. Terraform lifecycle apply (bucket expiration): human runs it.
3. Final audit rulings (deliverable 4).
4. THE FLIP — human-only, in this order: merge the phase-7 PR →
   set repo description/topics → Settings → Danger Zone → change
   visibility to Public → immediately enable branch protection on
   main (require lint/test/secrets/dbt/dag-verify checks) → add
   the repo link to CV/profile.

## Constraints

- Touch only what the checklist items require + README/DECISIONS/
  PLAN/CLAUDE.md/docs/. No new features. No new deps.
- Every screenshot referenced in the README must exist in
  docs/assets/ (a test or make check that asserts referenced asset
  paths exist is welcome and cheap).
- The README's case-study section is human-owned prose; the loop
  never finalizes it.
- Communication-style rules are ENFORCED on the README: the loop
  should grep its own draft for the banned adjectives before the
  curation STOP.

## Out of scope

- New pipeline capabilities. Renaming anything. History rewrites.
- Deploying anything. Post-public backlog items (a docs/BACKLOG.md
  is fine as a home for parked notes).

## Loop protocol

1. Checklist items (deliverable 3) first — mechanical, testable —
   in one or two commits on branch phase-7-packaging.
2. DECISIONS pass (2), then README draft (1) → STOP for curation.
3. After curation: hygiene (5), then the final audit (4) → STOP for
   rulings → apply rulings → deterministic re-verification only.
4. Final commit(s), summary: checklist item-by-item disposition, the
   asset inventory with what each image shows, audit result, the
   flip checklist restated for the human. Do not push. Do not flip.
