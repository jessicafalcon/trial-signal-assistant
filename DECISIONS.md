# DECISIONS

Why-not-X log. One entry per non-obvious choice.

## 2026-08-14 — Phase list joined to a single string

The API sends `phases` as a list (usually one entry, sometimes
`["PHASE1", "PHASE2"]`). `TrialRecord.phase` joins it with `/` —
`"PHASE1/PHASE2"` — so the field stays a flat string for dbt and Chroma
metadata, and the raw list is recoverable by splitting on `/`. `"NA"` is
kept verbatim rather than mapped to None: it means "not applicable"
(e.g. observational), which is information, unlike an absent field.

## 2026-08-14 — Interventions parsed as name strings only

`TrialRecord.interventions` keeps only each intervention's `name`; the
API's `type` (DRUG, DEVICE, BIOLOGICAL, …) and `description` are dropped.
Names are all the staging models and status-change marts need, and a flat
`list[str]` keeps the record simple. Revisit in Phase 5: the RAG layer
may want type and description for richer per-field embedding docs — at
that point extend the record rather than re-parse ad hoc.

## 2026-08-14 — Date formats corrected from corpus scan

The documented date formats ("January 2024", "January 15, 2024") did not
survive contact with the live API: a scan of every string field across all
1,738 AD studies found zero date fields in those shapes. The API v2 actually
returns two ISO precisions — "YYYY-MM-DD" (day) and "YYYY-MM" (month) — and
date structs can be absent entirely. CLAUDE.md and SPEC-01 were corrected to
the measured formats, and the parser requirement was made defensive: any
unknown format keeps the raw string with date_precision=None and a logged
warning instead of raising. Empirical findings supersede docs.

## 2026-08-14 — Neutral repo name

The repo is named after what it does (trial and safety signal assistance),
not after any target company. The project mirrors a specific company's
assistant pattern, but naming it after them would tie a public portfolio
piece to one employer and imply an affiliation that doesn't exist. A neutral
name keeps the repo reusable across applications and honest about being an
independent build. The pattern it mirrors is described in the README and
CLAUDE.md instead, where context can be given properly. 2026-08-14: CLAUDE.md
now describes the pattern generically too — the named reference belongs only
in the README case-study section (Phase 7), aligning with this decision.

## 2026-08-14 — Dual dbt targets: DuckDB (local/CI) + Snowflake (demo)

DuckDB is the default target because it is a zero-cost, zero-setup local
file: contributors and CI can run `dbt build` with no credentials, no
network, and identical results per the determinism policy. Snowflake exists
as a second target purely to demonstrate the same models running on a real
cloud warehouse with COPY INTO from S3 — the pattern employers actually run.
Keeping both in one profiles.yml proves the dbt code is warehouse-portable
rather than coupled to one engine. CI stays green without Snowflake
credentials existing at all (the trial isn't even activated yet).

## 2026-08-14 — Claude Code tooling ported from a prior project

Agents, hooks, and a /selfcheck command were ported from an earlier repo and
adapted (see "Project tooling" in CLAUDE.md). Non-obvious choices:

- The run-tests hook runs the full suite (`pytest -q`), not `make test`
  (currently `tests/test_parser.py` only): the hook should catch breakage in
  any future test file without editing the hook. Revisit if the suite ever
  gets slow.
- Agents keep Bash despite the report-only contract — they need it for
  `git diff` and pytest. The boundary is prompt-enforced (no Write/Edit in
  their tools line), not a permission wall; CLAUDE.md says so explicitly
  rather than claiming a stronger property than the config enforces.
- Accepted risk: `.claude/settings.json` is committed, so anyone opening
  this public repo in Claude Code auto-runs run-tests.py (and therefore
  pytest and conftest.py) on .py edits, without a permission prompt. This is
  the standard Claude Code hook model; review branches that touch
  conftest.py or .claude/ before opening them.
- Accepted risk: on red, run-tests echoes the last 15 lines of pytest output
  into the transcript. Pytest defaults don't print environment values;
  revisit before Phase 4 introduces real Snowflake/AWS credentials. Tests
  are network- and credential-free by policy, so the hook's output tail
  cannot echo secrets.

## 2026-08-14 — Hook revs SHA-pinned; CI token read-only

Moving CI lint to `pre-commit run --all-files` made CI clone and execute the
hook repos, so their `rev:` fields switched from tags (v0.16.3, 4.3.0) to the
tags' full commit SHAs: a tag is mutable and can be repointed upstream with no
visible change in this repo, while a SHA pin also satisfies the determinism
policy ("same inputs → same outputs"). For the same blast-radius reason,
ci.yml gained a top-level `permissions: contents: read` block so the
`GITHUB_TOKEN` can never write, whatever the repo default is. Deliberate
upgrades go through `pre-commit autoupdate`, which rewrites SHA pins. Both
changes came out of the security-reviewer pass on the CI edit.

## 2026-08-14 — Fixture data minimization: personal contact data removed

The original `fixture_page.json` and `fixture_dates_mixed.json` carried a
named investigator's direct email and phone (a `pointOfContact` block on
NCT02289989). This is verbatim public ClinicalTrials.gov registry data, so
re-publishing it discloses nothing new — it was removed on principle anyway:
a GitHub copy is indexable in ways the registry page may not be, and the
fixtures don't need it. SPEC-01's fixture criteria were amended (no
`pointOfContact` or direct emails/phones; investigator names in
`overallOfficials` remain acceptable) and both fixtures were re-captured
from the live API: the page envelope filtered to COMPLETED studies without
results, and the partial-date example replaced by NCT01138761 (same quirk,
no contact data). The prior fixture versions persist in local pre-push git
history — accepted and documented here rather than scrubbed, since the repo
has never been pushed and the data remains public either way.

## 2026-08-14 — Fixture parquet mode: pinned capture date, scoped dedupe

`make parse FIXTURES=1` (the CI path) pins ingest_date to the fixtures'
capture date (2026-08-14) instead of "today": a fixture run must produce
byte-identical output forever, per the determinism policy. Two fixture
files share one study (NCT06361992), so fixture mode dedupes by nct_id
(first occurrence, sorted file order) to satisfy the staging unique test;
real partitions are deliberately NOT deduped — a duplicate there is a
data problem the test should surface, not one the bridge silently
repairs. 2026-08-14 (phase 2 close ruling): fixtures mode originally
wrote into data/parsed/ and could overwrite the real same-date
partition; it now lands in data/parsed_fixtures/ (still under the
gitignored data/). A test pins that fixtures mode leaves real
partitions byte-identical. dbt's read path stays a FIXED literal
(data/parsed) — a first attempt parameterized it via env_var() in the
source's external_location, and the security probe showed the value
lands unescaped inside a SQL string literal: a quote-bearing
TRIALS_PARSED_ROOT injected arbitrary DuckDB SQL (verified by compile).
A validating macro was not an option (custom macros don't render in
source yml). So CI symlinks data/parsed -> parsed_fixtures instead:
zero SQL dynamism, injection class gone, and a drifted path fails loud
in CI because no real data/parsed exists there.

## 2026-08-14 — Bridge stores dates as strings; staging owns typing

trials.parquet keeps start_date and ingest_date as ISO strings — exactly
what the parser emits — and stg_clinical_trials casts them to DATE. One
layer (staging) owns SQL types, the bridge stays a dumb serializer of
TrialRecord, and casting an already-normalized ISO string is typing, not
the date re-parsing SPEC-02 forbids. The DuckDB file itself lives at
dbt_project/trial_signal.duckdb, not under data/: sqlfluff's dbt
templater opens the database during lint, and on a fresh checkout (CI's
lint job) data/ does not exist — verified empirically; DuckDB cannot
create parent directories. dbt_project/ always exists in a checkout, and
*.duckdb keeps the file out of git wherever it lives.

## 2026-08-14 — Staging grain ruled: (nct_id, ingest_date)

The source globs every ingest_date partition while SPEC-02 mandated a
unique test on bare nct_id — green with one partition, guaranteed red on
the second ingest that Phase 3 snapshots require. Ruling: the staging
grain is (nct_id, ingest_date), preserving the completeness time series
across partitions rather than keeping only the latest. The composite
uniqueness test and the snapshot reading only the latest partition land
in SPEC-03; the current bare-nct_id test stays valid exactly as long as
one partition exists, and its first failure is the signal that SPEC-03's
test swap is due.

## 2026-08-14 — Gitleaks allowlist: OR-default near-miss

Path-scoping the fixture-cursor allowlist (`paths = ^tests/`) as first
specified silently widened it: gitleaks `[[allowlists]]` blocks default to
`condition = "OR"`, so the path entry alone allowlisted every finding under
tests/ regardless of value. The mandated planted-token probe caught it
before commit — the probe, not the config review, is why the allowlist is
trusted. `condition = "AND"` is now explicit with a load-bearing comment.
Standing rule: no allowlist change lands without the probe pair (planted
random token must be caught; HEAD scan must be clean).

## 2026-08-14 — Synthetic day-0 seed: labeled provenance, deterministic pick

The snapshot mechanism only produces transitions when a second state
exists, and real registry changes take months. `seed_synthetic_day0.csv`
fakes the first state: four real AD-corpus nct_ids assigned
lifecycle-plausible PREDECESSOR statuses, so the first live snapshot run
detects four transitions immediately. The seed is never mistakable for
registry data: every row carries snapshot_source='synthetic_day0', the
column rides through the snapshot into the mart's prior_source/new_source,
and the seed schema.yml says "synthetic demonstration state, not registry
data" (CSV comment headers don't exist in dbt seeds). The four ids are the
LOWEST nct_id currently in each required successor status — a deterministic
rule reproducible from the corpus, not an editorial pick.
changed_detected_at (dbt_valid_from) is wall-clock and differs per run by
design: it records when the pipeline observed the change, which is the
fact change detection exists to capture; everything derived from it is
deterministic given the same snapshot history.

## 2026-08-14 — Fixture-mode day-0: second seed + day0_seed_scope var

The fixture corpus (11 studies) contains no RECRUITING trial, so SPEC-03's
four corpus transitions cannot all occur in CI. Per the spec's fallback, a
fixture-scoped variant seed (`seed_synthetic_day0_fixtures.csv`) seeds four
fixture nct_ids with plausible predecessors (mirroring three of the four
corpus transitions; the RECRUITING successor is replaced by
NOT_YET_RECRUITING → WITHDRAWN, the canonical pre-enrollment stop). The
snapshot picks the variant via a second var, day0_seed_scope
('corpus' default | 'fixtures'), consulted only in seed mode and failing
loudly on any other value — same pattern as snapshot_source. Alternatives
rejected: filtering one seed against the current corpus (fixture ids also
exist in the real corpus, so local runs would seed 8 rows, breaking the
exactly-4 contract); mutating the seed CSV in CI (edits committed files).

## 2026-08-14 — make snapshot pre-builds staging; dbt build includes snapshots

`make snapshot` runs `dbt run --select +snap_trial_status` before
`dbt snapshot`: from a clean database, the snapshot's input view
(stg_trials_current) doesn't exist yet and bare `dbt snapshot` fails; the
selector keeps the pre-build step aimed at exactly the snapshot's
ancestors. Verified empirically (dbt 1.12): `dbt build` INCLUDES snapshots
— SPEC-03's parenthetical guessed it excludes them. `make dbt` stays a
plain `dbt build` anyway: a live snapshot re-run inside build is a no-op
on unchanged data, and CI/DONE both order snapshot-day0 before any build.
Known hazard, accepted: running `make dbt` on a clean database BEFORE
`make snapshot-day0` baselines the snapshot with live statuses, and a
later day-0 seed then adds live→synthetic→live noise transitions. The
documented order (make reset → snapshot-day0 → snapshot → dbt) avoids it.

## 2026-08-14 — Snapshot hard-delete policy deferred to Phase 6

snap_trial_status sets no invalidate_hard_deletes: a trial that leaves
the corpus keeps dbt_valid_to null and reads as current forever. Ruled
deferred to Phase 6 (Airflow wiring), where the snapshot cadence is
decided, for a reason beyond scope: hard-delete invalidation interacts
badly with the seed-mode input switch. A seed-mode run presents only 4
nct_ids, so with hard-delete invalidation on, dbt would treat the other
~1,734 live trials as deleted and close every one of their rows —
snapshot-day0 must never run with that setting enabled, and the same
mechanism amplifies the documented day0-rerun hazard (a snapshot-day0
re-run already writes spurious synthetic rows; with invalidation it
would also close the entire live corpus). Phase 6 must resolve both
together (e.g. hard deletes only on live-mode runs, or a dedicated
delisted-detection model instead).

## 2026-08-14 — Pre-push audit closed by human risk decision

Four review rounds (one full-tree audit, three delta reviews, rulings on
every finding) ended with deterministic-only verification: the floor's four
checks, the three gitleaks probes, and git check-ignore spot checks. The
owner terminated further judgment review: the repo is private, the floor is
green, and history contains zero credentials. Remaining depth is the
phase 7 pre-public audit checklist in PLAN.md — scheduled for the public
flip, not forgotten.

## 2026-08-15 — Snapshot machinery is duckdb-only in phase 4

`make dbt-snowflake` excludes `snap_trial_status+` and all seeds: the
change-detection demo (day-0 seed, snapshot, mart_trial_status_changes,
idempotency proofs) runs on duckdb, while snowflake proves the
warehouse path (COPY INTO + staging + completeness mart). Running
snapshots on two targets would mean two divergent SCD2 histories with
wall-clock dbt_valid_from values — a second source of truth with no
demo value. Revisit only if Phase 6 moves orchestration to Snowflake.

## 2026-08-15 — Snowflake load via dbt run-operation, not a client script

`make load-snowflake` wraps `dbt run-operation load_raw_trials`
(scripts/load_snowflake.sh is a thin shim to keep the spec's script
path). Rationale: dbt-snowflake is already pinned, so the macro reuses
profiles.yml's env_var() credential wiring — no snowflake-connector
import, no second connection codepath, nothing new on the dependency
allowlist. RAW.TRIALS is created by the macro (create table if not
exists) as TRANSFORMER, so ownership covers dbt's reads with no extra
grants. Idempotency is COPY INTO's own load history (64 days): the
second run reports "Copy executed with 0 files processed."

## 2026-08-15 — Cross-target SQL: portable first, jinja only where forced

Snowflake has no `filter (where ...)` aggregate clause, so
mart_field_completeness moved to `sum(case when ... then 1 else 0 end)`
— arithmetic-identical on both engines, one code path, no conditional.
The only target conditionals are: the varchar[] cast of list columns
(duckdb) vs ARRAY passthrough (snowflake) in stg_clinical_trials, and
the source resolution in sources.yml (external parquet path vs
RAW.TRIALS). All branch on `target.type` — a compile-time constant
from profiles.yml — so the SPEC-02 no-env-var-into-SQL constraint
holds. Parity proof: staging count 1738 on both; completeness mart
rows byte-identical (2026-08-15).

## 2026-08-15 — Terraform: one converging apply, provider quirks pinned

SPEC-04 prescribed the standard two-apply flow for the storage
integration ⇄ IAM trust handshake; provider 2.19.0 exports the minted
IAM user ARN and external ID as computed attributes
(describe_output), so the integration is created before the role and
ONE apply converges — the post-apply `terraform plan` showing
"No changes" is the spec's convergence proof (verified 2026-08-15).
Non-obvious choices that came out of the apply sessions:

- New-generation resources (snowflake_storage_integration_aws,
  snowflake_stage_external_s3, snowflake_file_format_parquet) over the
  deprecated classics; only file_format_parquet still needs
  preview_features_enabled.
- The provider reads SNOWFLAKE_ACCOUNT (legacy field, hard error) and
  SNOWFLAKE_WAREHOUSE (session warehouse that doesn't exist pre-apply)
  from the environment: both must be unset in the terraform shell, and
  the account id is supplied split as SNOWFLAKE_ORGANIZATION_NAME /
  SNOWFLAKE_ACCOUNT_NAME (documented in terraform/README.md and
  .env.example).
- GRANT ... TO USER is case-sensitive through the provider (it quotes
  identifiers): TF_VAR_snowflake_admin_user must match SHOW USERS'
  NAME column exactly.
- The make targets pin the non-secret connection facts
  (TRANSFORMER / TRIAL_SIGNAL_WH / TRIAL_SIGNAL / ANALYTICS) rather
  than trusting .env: the demo must provably run least-privilege on
  the XS warehouse regardless of the caller's environment; only
  account/user/password come from .env.
- .terraform.lock.hcl is committed (provider checksum pins,
  determinism); state stays local and gitignored. The S3-scoped IAM
  user needed an inline policy widening to manage exactly
  role/trial-signal-snowflake-access — role-ARN-pinned, applied by
  the owner in the console, not by terraform.

## 2026-08-15 — Phase 4 review round: rulings F1-F16 applied

Four reviewer passes (code, security, functionality, coherence), owner
rulings applied in the phase-4 commit. Non-obvious outcomes recorded:

- Load idempotency is scoped, not absolute: COPY INTO skips only
  byte-identical files within its 64-day load history. A re-parse
  rewrites the parquet and re-loads into the append-only RAW.TRIALS;
  the staging grain test is the loud failure. Reset mechanics are
  deferred to Phase 6, decided together with invalidate_hard_deletes
  (same entry as the 2026-08-14 hard-delete deferral).
- The load macro hardcodes trial_signal.raw.trials instead of
  {{ target.database }}: profile fields are env-var-derived, and the
  SPEC-02 no-env-var-into-SQL constraint applies to run-operation
  macros too.
- dbt 1.12 auto-loads .env from the cwd (load_dotenv in its CLI), so
  any repo-root dbt invocation has .env values in-process and rendered
  yaml lands in the gitignored target/ artifacts. The make preflights
  guard make's env (which does NOT see .env) and fail closed; their
  value is the explicit error, not credential discovery.
- RAW.TRIALS DDL is a manual mirror of the bridge's parquet SCHEMA
  (cross-referenced comments both sides): extending TrialRecord in
  Phase 5 requires a hand migration there — create table IF NOT
  EXISTS never alters a live table.
- Four SPEC-05 input-surface requirements recorded (also in PLAN.md):
  (1) the embedder's input store must be chosen — no per-trial mart
  exists; candidates are stg_clinical_trials/stg_trials_current, the
  parquet, or RAW.TRIALS, and only duckdb holds snapshot history;
  (2) an incremental-rebuild change key must be defined — the only
  change signal today is overall_status via the snapshot's check_cols;
  (3) conditions/interventions are arrays on both targets and Chroma
  metadata values must be scalars — a flattening rule is needed;
  (4) the "dbt seeds and the RAG embedder import the parsers" comment
  (CLAUDE.md, fetch_clinical_trials.py docstring) is half-false — the
  seeds are hand-written CSVs; correct it when SPEC-05 fixes the
  embedder import for real.
- Standing rule added to CLAUDE.md (owner meta-ruling): security-
  reviewer should-fixes may exceed a spec's touch-list; deviation
  disclosed, never silent. Exercised here for .gitignore (terraform
  plan/crash-file patterns) and the secrets floor's new check (e)
  (no tfstate/tfvars/.terraform ever tracked).
