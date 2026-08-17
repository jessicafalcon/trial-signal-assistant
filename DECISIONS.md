# DECISIONS

Why-not-X log. One entry per non-obvious choice.

## Index by phase

- **0 Foundation / tooling**: Neutral repo name · Claude Code tooling
  ported · Hook revs SHA-pinned; CI token read-only · Gitleaks
  allowlist OR-default near-miss · Pre-push audit closed by human risk
  decision
- **1 Ingestion**: Phase list joined to a single string · Interventions
  parsed as name strings only · Date formats corrected from corpus
  scan · Fixture data minimization
- **2 Local warehouse**: Dual dbt targets · Fixture parquet mode ·
  Bridge stores dates as strings · Staging grain ruled
- **3 Change detection**: Synthetic day-0 seed · Fixture-mode day-0 ·
  make snapshot pre-builds staging · Snapshot hard-delete policy
  deferred (→ superseded by R1)
- **4 Cloud**: Snapshot machinery duckdb-only · Snowflake load via dbt
  run-operation (→ superseded by R2) · Cross-target SQL portable
  first · Terraform one converging apply · Phase 4 review round
  (F1–F16)
- **5 RAG**: RAG input surface / change key / flattening (F8) ·
  Dependencies duckdb and pyyaml pinned · mart_trial_documents
  duckdb-only · Claude model pinned · Sponsor names filterable, not
  searchable · Phase 5 review round
- **6 Orchestration**: R1 snapshot hard deletes · R2 delete-by-
  partition + COPY FORCE · Airflow Astro layout · Phase 6 review
  round · Local venv aligned to 3.11 · DAG runs local-first · Host and
  container dbt artifacts split
- **7 Packaging**: Pre-public checklist choices (below) · Flip step-4
  purge waived · External review dispositions · Observability slice
  (source freshness + ingest-history mart)

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
(Revisited 2026-08-15: the F8 ruling kept embedded documents to verbatim
registry free-text — brief_summary / detailed_description / why_stopped —
so interventions stay name-only. Parked, not forgotten.)

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
(2026-08-15 phase-7 curation ruling: the case study stays generic — no
company is named anywhere in the repo.)

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
  (Superseded 2026-08-15: hook wiring moved to the gitignored
  settings.local.json before the public flip — see the phase-7
  run-tests-wiring entry.)
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
no contact data). Resolution record (rewritten 2026-08-16 by owner ruling — this
paragraph originally accepted the residual "since the repo has never
been pushed"): that premise was invalidated when the repo was pushed,
and the final pre-public audit refused to let the flip proceed on a
justification written for a never-pushed repo. The history was
scrubbed 2026-08-16, before the flip, via blob replacement — the two
pre-scrub fixture blobs swapped for their scrubbed HEAD equivalents in
every commit that carried them; the contact name, email, and phone
grep to zero across the rewritten history (see the phase-7
history-rewrite entry for the mechanism and hash map).

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
(Landed in phase 3: tests/assert_stg_clinical_trials_grain.sql asserts
the composite grain; stg_trials_current carries bare-nct_id uniqueness
at the latest-partition grain.)

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
(Superseded 2026-08-15: resolved by R1 — hard_deletes='invalidate' on
live runs only, circuit-breaker-guarded; see the R1 entry below. Note
the config name: dbt ≥1.9 spells it hard_deletes, not
invalidate_hard_deletes.)

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
(Superseded 2026-08-15: R2's FORCE defeats load history by design —
idempotency is now delete + reload per partition; see the R2 entry.)

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
  (Superseded 2026-08-15: R2 replaced append-only with
  delete-by-partition + scoped COPY FORCE — see the R2 entry below.)
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

## 2026-08-15 — RAG input surface, change key, flattening (F8 resolved)

The embedder reads one store only: `mart_trial_documents`, built on
stg_trials_current (latest partition; duckdb target). Long format — one
row per (nct_id, doc_field) for brief_summary / detailed_description /
why_stopped — so each field embeds as its own document and why-stopped
questions retrieve the stop reason directly. The incremental change key
is `content_hash` = md5(doc_text), computed in SQL: the embedder skips
ids whose stored hash matches, so an unchanged mart re-embeds 0
documents. Chroma metadata values must be scalars, so conditions join
with '; ' (`conditions_flat`); nullable scalars (phase, sponsor_name)
coalesce to '' because Chroma also rejects nulls and 'NA' is a real
registry phase value that cannot double as the absent marker. Why not
embedding in dbt: dbt stays deterministic SQL; the Python embedder is a
thin consumer of the mart. Note: `make rag-build` downloads the pinned
model from Hugging Face on first run — the third sanctioned network
path beside `make ingest` and the cloud targets (never in CI).

## 2026-08-15 — Dependencies: duckdb and pyyaml pinned (owner-approved)

`duckdb==1.5.5` (the exact version dbt-duckdb already resolves) approved
per SPEC-05 deliverable 5 so the embedder and unit tests can read the
mart / run the mart's SQL expressions without going through dbt.
`pyyaml==6.0.3` (already installed transitively via dbt-core) approved
at the gate-1 ruling for `golden_questions.yml`. Both pinned in
requirements.txt and added to the CLAUDE.md allowlist in the same
commit; CI's test job installs both (in-memory SQL + yml validation —
still no network).

## 2026-08-15 — mart_trial_documents is duckdb-only on the demo target

`make dbt-snowflake` excludes `mart_trial_documents+` alongside the
snapshot subtree: the RAG store is built locally from duckdb, so a
Snowflake copy would be dead weight, and the mart's array_to_string/md5
SQL would need a cross-target rewrite for zero consumers. Same
reasoning as the 2026-08-15 snapshot exclusion; revisit if the demo
ever serves RAG from Snowflake (Cortex path, README production notes).

## 2026-08-15 — Claude model pinned to claude-sonnet-4-5-20250929

Determinism policy demands temperature 0 plus a pinned model version.
Current-generation models (Opus 5 / Sonnet 5 / Fable 5) reject the
temperature parameter outright, so the pin is the newest dated-snapshot
id that still accepts temperature=0. Intent is reproducibility of the
demo (same retrieval + same prompt → same answer as far as the API
allows), not model-quality maximalism (owner ruling 2026-08-15).
Revisit trigger: when this model family deprecates, or when the answer
quality needs a newer family — accepting that newer families drop
temperature control entirely and determinism then rests only on the
pinned id + grounded prompt.

## 2026-08-15 — Sponsor names are filterable, not semantically searchable

Golden-set curation dropped sponsor-phrased questions ("the Celldex
trial"): sponsor_name lives only in Chroma metadata, not in embedded
text, so semantic retrieval cannot find a trial by sponsor. Sponsors
are reachable via exact metadata filtering only; embedding a composed
header (sponsor + title) into doc_text was rejected this phase to keep
documents verbatim registry text. Rare drug tokens (difelikefalin,
piroctone) also retrieve poorly with all-MiniLM-L6-v2 at k=5 — a
reranking/hybrid-search note for the production-notes section, not a
phase-5 fix.

## 2026-08-15 — Phase 5 review round: rulings applied

Three reviewer passes (code, security, functionality); owner rulings
applied in the phase-5 commit. Non-obvious outcomes:

- Citations are now verified, not scraped: cited_nct_ids is
  intersected with the retrieved set; ids the model echoes from
  untrusted registry text land in a separate unverified_nct_ids key
  (S1 — extends the SPEC-05 CLI output contract by one key). Context
  documents are structurally fenced (<document> tags, angle brackets
  escaped out of bodies, ids trusted from attributes only) instead of
  prose-fenced (S2).
- The embedder deletes ids that left the mart, so stale documents
  cannot be retrieved or cited; "store now holds" logs
  collection.count(), not the mart count (C2/F1). doc_text is trimmed
  before hashing so whitespace-only registry churn never re-embeds
  (C8).
- The refusal question is excluded from the retrieval denominator
  (its pass was by construction); citation keeps all 10 (C5).
- recreate_raw_trials.sh requires CONFIRM=1 before dropping the live
  table (S4); make ask single-quotes its interpolations (S3).
- C1 (claimed ruff-format violations) dismissed as empirically false:
  three independent green lint runs beat a read-only reviewer
  assertion. Lesson recorded: verify tool-behavior claims by running
  the tool before ruling.
- Dependency-widening provenance (S5, sufficiency confirmed): duckdb
  was pre-approved in SPEC-05 deliverable 5; pyyaml approved in the
  gate-1 owner reply. Accepted residual (F2): make rag-build/ask ping
  the HF Hub even with a warm cache — offline reproducibility rests
  on the local cache + pinned revision. Deferred to the phase-7
  checklist: richer phase matching in the RAG CLI (C4).

## 2026-08-15 — R1: snapshot hard deletes on, mode-gated, circuit-broken

snap_trial_status now sets hard_deletes='invalidate' — but only when
snapshot_source='live'; seed-mode runs get 'ignore'. Rationale: the
phase-3 deferral's hazard was the seed-mode input switch (4 nct_ids
presented → ~1,734 live rows would read as deleted), and gating the
config on the same var that switches the input kills that class of
accident structurally — snapshot-day0 cannot invalidate anything, and
a day0 re-run stays exactly as (non-)hazardous as before. Live runs
are guarded by assert_latest_partition_not_collapsed, a singular test
run between the staging build and dbt snapshot (make snapshot, and a
dedicated DAG task): it fails if the latest partition holds fewer than
circuit_breaker_min_ratio (default 0.8) of the prior partition's rows.
0.8 because the AD corpus (~1,738 trials) moves by single-digit counts
a day and the registry essentially never removes studies — a ≥20%
overnight drop is a collapsed ingest (truncated pagination, partial
response), not registry reality. Verified 2026-08-15: a 100-row
synthetic partition trips the breaker before the snapshot runs; a
1,733-row partition passes it and closes exactly the 5 missing trials
(dbt_valid_to stamped, no successor row, no phantom transition in
mart_trial_status_changes). Known edge, accepted: a delisted trial
that later reappears with an unchanged status produces a same-status
row pair in the mart (documented in snapshots/schema.yml).
Scope cuts, declared: (1) the delisting signal is write-only this
phase — a closed row (dbt_valid_to set, no successor) surfaces in no
mart, README, or RAG document; a delisted-trials mart is future scope,
not an accident. (2) The breaker compares only the latest partition to
its immediate prior at a fixed 0.8: an 86% single-day truncation, a
multi-day slow drift, and an EMPTY latest partition all pass — the
empty case is harmless only because stg_trials_current's own
max(ingest_date) then re-reads the prior day (two independent max()es,
recorded here so a refactor of either knows about the other).

## 2026-08-15 — R2: Snowflake load is delete-by-partition + scoped COPY FORCE

make load-snowflake is now per-partition: the macro deletes
RAW.TRIALS rows for the target ingest_date, then COPYs only that
partition's stage path with force = true. FORCE is load-bearing, not
belt-and-braces: after the delete, an unchanged file is still in
COPY's 64-day load history, so a re-run without FORCE would delete
the rows and load 0 files — an emptied partition. delete + scoped
FORCE means any same-partition re-run (byte-identical file OR a
re-parse) converges to the file's current contents; the phase-4
append-duplicate failure mode (grain test as the loud alarm) is gone.
Cost accepted: an unchanged partition is rewritten on re-load (one
partition per call; other partitions untouched). The partition value
reaches SQL text, so it is regex-pinned to \d{4}-\d{2}-\d{2} in both
the shell entry point and the macro (compile error otherwise) —
SPEC-02's injection constraint applied to the one dynamic literal.
Default partition = latest local data/parsed dir; DATE= picks one;
ALL=1 loops all local partitions (the recreate_raw_trials re-load
path, which previously relied on one all-files COPY).

## 2026-08-15 — Airflow: Astro project layout, BashOperator-on-make, skip mechanics

Phase-6 orchestration choices that the spec left open:

- Layout: `astro dev init` scaffolded into airflow/ (never repo root);
  the repo-root dags/ stub dir was RELOCATED into airflow/dags/
  (removed, not pointered — Astro's scheduler only parses its own
  dags/, so a root copy would be dead code). The runtime pin is
  Astro Runtime 3.3-2 = Airflow 3.3.0; apache-airflow==3.3.0 is the
  matching host-side test dep (owner ruling: isolated in
  airflow/requirements-dagtest.txt, installed only by make dag-verify;
  install verified to change zero existing pins, pip check clean).
- Every task is a BashOperator cd-ing into the repo mount and calling
  make: make is the tested interface (pytest + CI exercise it), so
  provider operators (S3/Snowflake/dbt) would add a second, untested
  connection codepath. Cost accepted: Airflow sees each step as
  opaque.
- No-credentials skip: a ShortCircuitOperator heads the cloud
  TaskGroup, returning False (with the missing names, never values,
  logged as the reason) when SNOWFLAKE_*/AWS_PROFILE are absent;
  ignore_downstream_trigger_rules=False + none_failed on dbt_duckdb
  lets the skip stop at the local path, and verify_parity's default
  all_success rule inherits the skip. Chosen over a BranchOperator
  (two explicit branches to maintain) and over failing fast (a
  no-cloud environment is a supported demo mode, not an error).
- Credential surface: runtime-only via docker-compose.override.yml
  (env_file ../.env on the scheduler; ~/.aws mounted read-only).
  Empirically verified 2026-08-15: bare `docker run ... env` on the
  built image shows zero credential vars (the one SNOWFLAKE match is
  AIRFLOW_SNOWFLAKE_PARTNER, Astro's provider-attribution tag) and no
  .env file in any layer — build context is airflow/ and .dockerignore
  excludes .env. Gotcha recorded: the astro user's HOME is /home/astro,
  not /usr/local/airflow — the ~/.aws mount must target /home/astro/.aws
  (first run failed on this; aws could not find the profile).
- In-container pips mirror the repo's exact pins (requests, pyarrow,
  dbt-core/duckdb/snowflake, duckdb, sentence-transformers, chromadb);
  apt adds make + awscli. anthropic/pyyaml stay out — make ask/eval
  are not DAG tasks.
- Same-day idempotency is logical, not byte-level: the second trigger
  re-uploaded the parquet (a re-fetch is not guaranteed byte-identical
  — API response ordering), but R2 delete+FORCE converges the
  partition, the snapshot fingerprint is unchanged, and rag_build
  embeds 0. The byte-determinism of a re-fetch was never the claim.
- Observed, expected: unpausing the DAG fires the just-completed daily
  interval alongside a manual trigger (catchup=False only suppresses
  older intervals); max_active_runs=1 serializes them.

## 2026-08-15 — Phase 6 review round: rulings applied

Four reviewer passes (code, security, functionality, coherence), owner
rulings applied before the phase-6 commit. Non-obvious outcomes:

- make circuit-breaker is a dbt build (+selector), not a bare dbt
  test: it now builds the staging view it reads, so it is
  self-sufficient on a clean database and as DAG task 3 (the reviewed
  version failed on any fresh clone). make snapshot depends on it.
- The breaker is excluded from make dbt-snowflake: it guards the
  duckdb-only snapshot, and a thin Snowflake partition usually means
  "not loaded yet" (R2 default = latest only), not "ingest collapsed"
  — the alarm would name the wrong cause. Snowflake stays 17/17.
- Credential passthrough narrowed (blast-radius ruling): compose
  passes exactly SNOWFLAKE_ACCOUNT/USER/PASSWORD + AWS_PROFILE from
  the astro dev start shell (no env_file — the whole .env, including
  ANTHROPIC_API_KEY, previously entered the container), and only
  ~/.aws/{config,credentials} are mounted. Side effect: a fresh clone
  with no .env starts cleanly and the cloud group skips.
- apache-airflow install is constrained: make dag-verify resolves
  airflow/requirements-dagtest.txt against Airflow's published
  constraints file for the venv Python and fails loudly on
  interpreters without one (3.11-3.13 published; owner ruling — the
  venv requirement is in README Setup). Allowlist line confirmed as
  written: test-only, isolated.
- The load macro fails if COPY loads 0 rows: the delete commits first,
  so an empty stage path (never-synced partition, bad DATE=) would
  otherwise silently empty the partition. verify_parity's mismatch
  output names the recovery (make load-snowflake ALL=1) because a
  skipped cloud day leaves Snowflake one partition behind by design —
  no self-healing in the DAG (owner ruling: document, don't ALL=1
  daily).
- Every DAG task has an execution_timeout (30 min network / 15 min
  local): max_active_runs=1 means one hung task otherwise blocks the
  schedule forever.
- Test additions (owner: "all item-26 tests"): bash_command → make
  target map with forbidden-target assert (snapshot-day0, reset), make
  targets must exist in the Makefile, operator types,
  ignore_downstream_trigger_rules=False, execution timeouts,
  start_date/depends_on_past, the creds-gate callable (names logged,
  never values), breaker SQL boundary cases in duckdb (800/1000
  passes, 799/1000 fires; historical dips don't re-fire), and R2
  shell partition selection via a stubbed DBT. Suite: 73 → 98.
- Left as-is, recorded: the creds gate treats a whitespace-only value
  as present (fails later at Snowflake auth after retries) — behavior
  change was not ruled, so it is documented rather than fixed.

## 2026-08-15 — Local venv aligned to CI's Python 3.11

The venv was rebuilt from 3.14 to 3.11 (owner ruling) so local and CI
share one interpreter — closing the phase-0 alignment recommendation.
3.14 had surfaced three incompatibilities: no Airflow constraints file
exists for it (make dag-verify's loud-fail case), the Snowflake
connector's vendored-requests version check warns on 3.14-era
urllib3/charset pins on every invocation, and CI (3.11) and local DAG
tests never exercised the same interpreter. README Setup names 3.11 as
the reference version (3.12/3.13 acceptable, 3.14 unsupported for
dag-verify). Observed during the rebuild: Airflow's constraints file
serves Airflow's test matrix, not this repo's stack — it downgraded
cryptography to 48.0.1 (breaking pyopenssl → snowflake-connector) and
moved pathspec/certifi/more-itertools off dbt's ranges. make
dag-verify now restores the ranges both stacks accept and runs
`pip check` as a loud final gate.

## 2026-08-15 — DAG runs local-first; cloud moved downstream

Post-phase-6 owner ruling (external architecture review of d67fe38),
explicitly superseding SPEC-06 deliverable 2's task chain, which put
dbt_duckdb downstream of dbt_snowflake. That order was wrong: with
creds present, a cloud failure (S3/Snowflake outage) marked dbt_duckdb
upstream_failed — none_failed tolerates skips, not failures — so an
outage cost the day's snapshot. The asymmetry decides the order: a
missed cloud load is recoverable any time (make load-snowflake ALL=1,
delete+FORCE converges), while a missed snapshot is recoverable only
by same-day manual intervention (next day a new partition becomes
stg_trials_current; the transition itself still lands on the next run,
but its dbt_valid_from timing — and any A→B→A flip inside the gap —
is gone). New graph: ingest → parse → breaker → dbt_duckdb →
verify_idempotent → {rag_build, cloud chain} → verify_parity.
Serialization of the two dbt paths is kept (they share dbt_project/'s
target/ and logs/ — never two dbt processes at once); rag_build may
overlap the cloud chain because it is not a dbt process. dbt_duckdb's
none_failed rule is gone (nothing above it can skip now); the
ShortCircuit gate's skip covers only cloud tasks + verify_parity. The
SPEC-06 chain had no recorded rationale — it was narrative order; this
entry is the rationale the original choice lacked. The phase-6
verification runs on record executed the old order; the reorder
postdates them.

## 2026-08-16 — Host and container dbt artifacts split (cache poisoning fix)

dbt's partial-parse cache (target/partial_parse.msgpack) stores
absolute file paths, and host + container share the repo mount at
different absolute paths — so whichever environment ran dbt last
poisoned the cache for the other. Observed twice on 2026-08-15: an
in-container seed load failed on /Users/... paths after a host-side
make test (whose cloud-guard test invokes dbt). Fix: the DAG's make
prefix sets DBT_TARGET_PATH/DBT_LOG_PATH to container-only dirs
(dbt_project/{target,logs}_container/, gitignored), so the two
environments never read each other's artifacts; the host keeps dbt's
defaults untouched. Chosen over a dbt_project.yml target-path change
(would move the host too and break sqlfluff's dbt templater
expectations) and over "clear target/ before DAG runs" (a manual step
that the overnight scheduled run can't perform). Proven by recreating
the failing sequence with the fix: host dbt build, then in-container
make dbt — 67/67 PASS with both artifact dirs coexisting. Residual,
accepted: the duckdb FILE is still shared — host dbt must not run
while a DAG run is active (compose comment).

## 2026-08-15 — Phase 7 packaging: pre-public checklist choices

Non-obvious outcomes of clearing PLAN.md's pre-public audit checklist
(the mechanical dispositions live inline in that checklist):

- Gitleaks self-governance: CI guard chosen over CODEOWNERS. A
  sole-maintainer repo cannot require code-owner review without
  blocking its own PRs (you cannot approve your own), so the secrets
  job instead reruns the full-history gitleaks scan with the BASE
  branch's .gitleaks.toml on every PR — an allowlist widening then
  fails CI for exactly the diff it tried to mask, forcing human
  review. .gitignore got no twin guard: floor checks (a)/(b)/(e) read
  the git index and history directly and never consult .gitignore.
- Bucket name/prefix: sync-enforced, not single-sourced. `terraform
  output` cannot feed make s3-sync because the DAG container that runs
  it has no terraform binary (and CI has no state); a pytest pins the
  Makefile values equal to terraform's defaults instead, so drift is a
  loud test failure rather than a silent mis-upload.
- stg_trials_current excluded from the snowflake target
  (stg_trials_current+ in make dbt-snowflake): its only consumers —
  the snapshot and mart_trial_documents — are duckdb-only by earlier
  rulings, so the view was dead weight there. Node-set diff verified
  the exclusion drops exactly the view and its five tests; the
  snowflake build is 12 nodes from here on (was 17).
- S3 noncurrent-version expiry set to 30 days (plus 7-day abort of
  incomplete multipart uploads): the daily DAG rewrites the same-day
  key per re-run, so noncurrent versions accrue per run; 30 days keeps
  a month of accidental-overwrite recovery while capping storage
  growth. Current versions never expire — the landed data is the
  product.
- persist-credentials: false on EVERY checkout, not only the secrets
  job the checklist named: no CI job pushes, so no job needs the token
  on disk; the narrow reading would have left five jobs carrying it
  for no reason.
- Action SHA pins record the resolved tag in a trailing comment
  (# v4.4.0 etc.); deliberate upgrades re-resolve via
  `git ls-remote https://github.com/<owner>/<repo> refs/tags/<tag>`
  and move pin + comment together.
- Author-email posture: verified 2026-08-15 — every author and
  committer email in the full history is a GitHub noreply address
  (102609780+jessicafalcon@users.noreply.github.com, plus GitHub's own
  noreply@github.com on web-UI merges). The public flip therefore
  discloses no personal email; nothing to scrub, no history rewrite
  ever needed for this.
- LICENSE is MIT (the default for a portfolio artifact meant to be
  read and reused); plain MIT with the GitHub handle as holder
  (owner-confirmed at the phase-7 ruling round).
- S3 lifecycle residuals, named and accepted (review note 6): (i) a
  future delete marker — a manual `aws s3 rm`, or `--delete` ever added
  to the sync — demotes the live object to noncurrent, and 30 days
  later the expiry makes that loss permanent; accepted because data/
  is re-derivable from the ClinicalTrials.gov API. (ii) Delete markers
  themselves accumulate (expired_object_delete_marker unset); accepted
  at this bucket's scale. The "current versions never expire" claim in
  s3.tf holds only while no delete marker is written.

## 2026-08-15 — run-tests hook wiring moved local-only (inbound-PR surface)

The phase-0 accepted risk — committed .claude/settings.json auto-runs
run-tests.py (hence pytest, hence conftest.py) on .py edits for anyone
opening the repo in Claude Code — was re-reviewed before the public
flip and re-ruled: on a public repo, checking out an inbound PR branch
and opening it in Claude Code would auto-execute attacker-controlled
code with no prompt. The wiring (the hooks block) moved to the
gitignored .claude/settings.local.json; the hook script stays
committed and documented, with the exact re-enable block in CLAUDE.md.
Chosen over the alternative posture (keep it committed plus a written
"review inbound branches first" rule) because a deterministic control
beats vigilance — the same principle as the rest of the security
layers. What this does NOT cover, on purpose stated: running pytest on
an inbound branch still executes that branch's conftest.py — no
configuration closes that; the review-before-pytest rule in CLAUDE.md
is the only mitigation and it is a human one.

## 2026-08-15 — One sanctioned gitleaks exception channel

gitleaks accepts exceptions from three places: the config's
[[allowlists]], inline `# gitleaks:allow` comments, and a
.gitleaksignore file. Only the first is guarded (CI reruns the scan
with the BASE branch's .gitleaks.toml on every PR), so the other two
were a bypass a PR could ship alongside the secret they mask —
defeating all three scan invocations at once (phase-7 scoped review,
should-fix 1; full defeat probe-proven in a throwaway repo). Closed
mechanically, each by the mechanism that actually works: inline
allows by --ignore-gitleaks-allow on every gitleaks invocation
(probe-proven — the planted allow-comment finding resurfaces);
the ignore-file by floor check (g) at the index and the working tree
(--gitleaks-ignore-path was probed INERT against a repo-root
.gitleaksignore on the pinned 8.30.1 and dropped as a false control).
Principle recorded: an exception channel is only acceptable if a
guard the PR cannot touch reviews it — .gitleaks.toml is that
channel; everything else is closed.

## 2026-08-15 — Check (g) scope: index + working tree, not history

The first cut of check (g) scanned index + full history like its
sibling (e) — and immediately fired on genuine history: b42d75f
(2026-08-14) added a .gitleaksignore, 561c593 removed it one commit
later when its entries migrated to the value-scoped .gitleaks.toml;
the content was inspected 2026-08-15 and held only the two benign
ClinicalTrials.gov pagination-cursor fingerprints. History rewrites
are out of scope, and on inspection history coverage guarded a
non-mechanism anyway: gitleaks reads .gitleaksignore from the
CHECKOUT at scan time, so a deleted historical copy cannot mute any
scan — unlike a historical .env or tfstate blob, which stays
readable forever and is why (a)/(e) do scan history. Ruled scope:
the index (a PR can only ship tracked files) plus the working tree
even untracked (a local copy still mutes a local pre-push run) —
the two boundaries where the file can act.

## 2026-08-15 — Floor check (f) accepted residuals

Check (f) is index-only and shape-based, on purpose: it asserts the
CURRENT .env.example ships bare keys (non-comment lines are exactly
KEY=; comment lines must not contain a KEY=<nonempty> shape). Two gaps
are accepted and assigned to other layers rather than widened here:
a value present only in HISTORICAL .env.example blobs, and prose
secrets in comments that carry no "=" shape — both are what checks
(c) (secret shapes over all history) and (d) (gitleaks over all
history, exception channels closed) exist for. Widening (f) into a
general content scanner would duplicate (c)/(d) with a weaker,
hand-rolled pattern set. A CRLF-committed .env.example fails closed
(every line flags, numbers only); no CR normalization on purpose —
stripping CRs would loosen the pattern (2026-08-16 note iii).

## 2026-08-16 — Floor skip flag is argv, not environment

The pin-bump skip for check (d) first shipped as an env var
(AUDIT_SKIP_GITLEAKS=1) and was replaced by a --skip-gitleaks argument
in the same unpushed branch (no compatibility shim — the env variant
never reached main). Why: an env var is ambient by nature, so anything
honoring it is fail-open to every shell and workflow scope that can
export it — a developer's exported var silently downgraded every local
pre-push, and a workflow-level env: block could reach the HEAD floor
run on push-to-main. Ambient environment cannot inject argv, so both
vectors cease to exist rather than being narrowed — no CI-marker
gating, no pin-empty step. Same shape as dropping
--gitleaks-ignore-path: when a control is fail-open by construction,
remove the construction. The flag's sole legitimate caller is ci.yml's
base-script guard.

## 2026-08-16 — Phase-7 review loop terminated by owner ruling

Each scoped security pass had begun reviewing the previous pass's
fixes with falling severity, so the owner ended the regress: one final
scoped pass over the entire unpushed delta ran 2026-08-16 and found
0 secret / 0 critical (floor 7/7 verbatim-green, every high-entropy
string in the delta a lock hash / action SHA / release checksum, all
security-relevant changes hardening-direction and documented). Per
the same ruling, its remaining should-fix and notes are recorded in
docs/BACKLOG.md instead of blocking — see B1–B4 there — and the
branch is push-ready. Same principle as the 2026-08-14 pre-push
audit closure: deterministic checks green, judgment review ended by
explicit human risk decision, residual depth parked in a named place.

## 2026-08-16 — History rewrite: owner-ruled exception, one-time scrub

SPEC-07 put history rewrites out of scope; the final whole-tree audit
found the one thing that outranks that constraint — a named third
party's direct email and phone in reachable history (pre-scrub fixture
blobs at the phase-1 capture commit), with an acceptance whose stated
premise ("never been pushed") had become false. Owner ruling: scrub
before the flip; the constraint gets this single recorded exception.
Mechanism: git-filter-repo blob replacement, NOT deletion — the two
offending blobs were swapped for the scrubbed HEAD versions of the
same files, so every historical commit stays internally valid.
git-filter-repo is a one-time local tool sanctioned by the ruling; it
is not a project dependency. Invariants verified: HEAD tree
byte-identical before/after (f5390888…); the contact's name, email,
and phone grep to ZERO across all rewritten history (strings derived
locally, never written to any output or file); the pre-scrub blob
objects are gone from the object store; floor 7/7 and the full DONE
command green on the rewritten history. The force-push and the
GitHub-side purge of cached unreachable objects are human gates
(docs/public_flip_checklist.md).

Load-bearing hash map (old → new; docs keep old hashes in prose as
historical references — this table is the translation):

| what | old | new |
|---|---|---|
| phase-1 fixture capture (carried PII) | 904b903 | dcfb2ad |
| fixture re-capture / scrub | 4904246 | 03fa12c |
| audit rulings (added .gitleaksignore) | b42d75f | 71bc456 |
| value-scoped allowlist (removed it) | 561c593 | 1545546 |
| phase-6 reorder review target | d67fe38 | 0aa6375 |
| merge PR #2 (phase 2) | 79fef1d | c234221 |
| merge PR #3 (phase 3) | fb52ac2 | a89efe5 |
| merge PR #4 (phase 4) | 9b56a5d | 30c4fd8 |
| merge PR #5 (phase 5) | 961a457 | fb0099f |
| merge PR #6 (phase 6) | 7867af6 | 0d1d672 |
| merge PR #7 (demo capture) | 0d9bf79 | 3f09cbf |
| merge PR #8 (phase 7) | 9ceba92 | 1be3f36 |

Also recorded here per the same ruling — the final audit's two notes
are owner-accepted as flagged: the live S3 bucket name in
terraform/variables.tf's default is an existence-only disclosure on a
hardened bucket (public-access block, TLS-only policy, scoped
read-only grant), and the $2.25 spend figure is intentional README
evidence, not an identifier.

## 2026-08-16 — Flip step 4 waived: cached pre-scrub history accepted

Owner ruling: the GitHub-side purge (public_flip_checklist.md step 4)
is waived — no support request, no repo delete-and-recreate. PR
history #1–#8 is kept and the flip proceeds directly from step 3 to
step 5. What remains: the pre-scrub commits persist on GitHub via
refs/pull/*/head and direct SHA URLs (rendered PR diffs included);
they do NOT reach default clones, which don't fetch pull refs — the
step-3 fresh-clone greps still expect zero. Why accepted: the only
scrubbed content is one investigator's contact details, verbatim
public ClinicalTrials.gov registry data — no secrets (floor 7/7;
final scoped pass 0 secret / 0 critical), nothing not already public.
The scrub's principle (don't be the indexable copy) holds for every
clone and the browsable tree; the residual sits in PR metadata and
takes deliberate lookup. Weighed against it: losing all PR provenance
(delete-and-recreate), or a support path of uncertain outcome
(GitHub's removal policy targets private information; already-public
registry data may not qualify). The hash map above stays as-is — the
residual is accepted openly, and stripping old SHAs would obscure it,
not remove it. This amends the history-rewrite entry's closing line:
the force-push stays a human gate; the purge gate is dropped.

## 2026-08-16 — External review dispositions (pre-flip)

A practitioner reviewed the repo before the public flip and raised
five findings. Ruled item-by-item; the flip waits until the ruled
work lands:

1. **Change detection never runs on Snowflake** (snapshot machinery
   duckdb-only; parity compares only staging + completeness) —
   IMPLEMENT: seeds + snapshot + mart_trial_status_changes on the
   snowflake target, circuit breaker ordered after the load, parity
   extended to transition values (dbt_scd_id fingerprints hash
   target-local timestamps, so parity compares mart values, never
   fingerprints). Reverses the 2026-08-15 duckdb-only scoping; that
   entry's premise (prove the warehouse path, not a second source of
   truth) lost to "the flagship feature must run on the flagship
   platform".
2. **Hand-rolled COPY INTO where Snowpipe exists** — DOCUMENT: the
   determinism/replayability trade stated unprompted in README
   production notes; Snowpipe named as the at-volume default.
3. **Airflow layer is thin** (no data-awareness, local-only) —
   DOCUMENT: scale path (assets, Cosmos, deferrable sensors, managed
   deployment) in production notes. The wrapper pattern itself stays —
   one definition per task, testable without Docker.
4. **Chroma is a second, ungoverned data platform** — DOCUMENT +
   backlog: Cortex Search convergence path puts retrieval inside the
   warehouse governance boundary; Chroma stays for the laptop demo.
5. **Observability stops at exit codes** — SPLIT: dbt source
   freshness + a deterministic ingest-history mart implemented (cheap,
   same-warehouse, demos well); alerting path, terraform remote
   backend, incremental fetch, and a credentialed scheduled parity job
   stay documented answers (production notes) — "no cloud creds in
   CI" is posture, not an accident.

## 2026-08-16 — Observability slice: source freshness + ingest history

External-review item 5's implemented half. dbt source freshness is
the project's one deliberately time-dependent check: staleness is a
property of wall-clock time by definition, so it can never satisfy
"same inputs, same outputs" — it is a monitoring gate (same family
as the circuit breaker), and its result feeds no transform.
Thresholds: warn at 2 days (daily cadence plus a day of grace),
error at 7. Live/local only — CI's fixture partition is pinned to
2026-08-14 and would be eternally stale by design. loaded_at_field
is cast(ingest_date as timestamp) because the bridge stores dates as
strings on both targets. mart_ingest_history stays fully
deterministic (pure SQL over staging's partitions): rows and
distinct studies per partition, delta and ratio vs the prior one
(the circuit breaker's own quantity, kept visible after the fact),
and the gap in days. Builds on both targets — warehouse-side
observability was the reviewer's point.
