# CLAUDE.md — Trial & Safety Signal Assistant

## What this is

A portfolio-grade data + GenAI pipeline: ingests public clinical trial data
(atopic dermatitis) from ClinicalTrials.gov, models it with dbt on a dual
warehouse (DuckDB locally/CI, Snowflake for demo), tracks trial status
changes over time via dbt snapshots, and answers natural-language questions
("why was this trial withdrawn?") through a RAG layer with cited Claude API
answers. It mirrors an industry assistant pattern (unified data platform
+ agentic Q&A instead of dashboard-hunting) at small scale.

Built by a developer who is NEW to dbt and Airflow — see Teaching rule below.

## Architecture

```
ClinicalTrials.gov API v2
        │  (ingest/fetch_clinical_trials.py — tested parser)
        ▼
data/raw JSON ──► parser bridge ──► data/parsed parquet (ingest_date partitions)
        │
        ├──► DuckDB (local dev + CI target — reads the parquet directly)
        └──► aws s3 sync ──► S3 parsed/ landing [Terraform, eu-west-3]
                                   └──► COPY INTO Snowflake RAW.TRIALS
                                        (external stage; demo target)
        │
        ▼
dbt: staging ──► snapshots (SCD2 on overall_status; duckdb only) ──► marts
        │
        ▼
Embeddings (sentence-transformers, per-field docs) ──► Chroma (+ metadata)
        │
        ▼
RAG retrieval ──► Claude API ──► grounded answer with NCT citations
```
Control plane: Airflow DAG (Astro, daily) · GitHub Actions CI · Terraform.

## Repo map

- `specs/` — agent-loop task specs. Each has ONE done command. Read fully first.
- `ingest/` — API fetching + pure parsing functions (dict in, TrialRecord out).
- `tests/fixtures/` — captured real API payloads. READ-ONLY ground truth.
- `dbt_project/` — profiles.yml has two targets: `duckdb` (default), `snowflake`.
  `models/` staging + marts, `snapshots/` SCD2, `seeds/` synthetic day-0
  CSVs, `tests/` dbt singular tests (distinct from pytest's tests/),
  `macros/` run-operation macros (the Snowflake COPY INTO load path).
- `scripts/` — secrets_audit.sh (deterministic pre-push floor),
  load_snowflake.sh (self-contained Snowflake load entry point),
  verify_parity.sh (cross-target row count + completeness compare), and
  recreate_raw_trials.sh (RAW.TRIALS schema migration: drop + recreate).
- `rag/` — embedding build, query layer, `eval/` golden questions + scorer.
- `airflow/` — Astro project (local Docker only, never CI): Dockerfile
  pinned to Astro Runtime 3.3-2 (= Airflow 3.3.0),
  `dags/trial_safety_pipeline.py` (the daily DAG; every task calls a
  make target), docker-compose.override.yml (repo mount + runtime .env
  passthrough), requirements.txt (in-container task deps),
  requirements-dagtest.txt (host-side DagBag test dep, isolated).
- `terraform/` — S3 + Snowflake infra.
- `docs/` — human-executed checklists (demo_checklist.md).
- `data/` — gitignored. `data/raw/` JSON, `data/parsed/` parquet (dbt's
  input), `data/parsed_fixtures/` fixture-mode parquet (CI symlinks it
  to data/parsed), `data/chroma/` vector store.
- `DECISIONS.md` — why-not-X log. Add an entry for every non-obvious choice.

## Commands (macOS, pip + venv)

- `make setup` — create .venv, pip install -r requirements.txt, pre-commit install
- `make test` — pytest over tests/ (parser + parquet bridge; no network
  calls allowed in tests)
- `make ingest` — live fetch AD trials → data/raw/ (network; never run in CI)
- `make parse` — parser → parquet bridge into data/parsed/; FIXTURES=1
  parses tests/fixtures/ into data/parsed_fixtures/ (CI mode)
- `make dbt` — dbt build --target duckdb (default local/CI definition of
  green; dbt build INCLUDES the snapshot — see ordering below)
- `make snapshot-day0` — seed + snapshot the labeled synthetic day-0
  state; FIXTURES=1 selects the fixture-scoped seed variant (CI)
- `make snapshot` — live snapshot (builds the staging views, runs the
  circuit breaker, then snapshots)
- `make circuit-breaker` — fails if the latest parsed partition holds
  < circuit_breaker_min_ratio (0.8) of the prior partition's rows;
  guards the snapshot's hard-delete invalidation (R1)
- `make verify-idempotent` — re-runs the live snapshot; fails if row
  count or dbt_scd_id fingerprint changed
- `make verify-day0-count` — fails unless the mart holds exactly the 4
  seeded day-0 transitions (CI runs it after the fixture sequence)
- `make reset` — delete the local DuckDB file (clean state)
- `make s3-sync` — aws s3 sync data/parsed/ to the landing bucket
  (idempotent; needs aws CLI + AWS_PROFILE from .env)
- `make load-snowflake` — per-partition load of RAW.TRIALS (R2):
  delete the partition's rows, COPY its stage files with FORCE — a
  same-partition re-run converges. Latest local partition by default;
  DATE=YYYY-MM-DD picks one, ALL=1 loads every local partition
- `make dbt-snowflake` — dbt build --target snowflake, excluding
  stg_trials_current+ (the view, snapshot machinery, and the RAG doc
  mart are duckdb-only — phase-7 scoping) and seeds. Both snowflake targets
  preflight-fail on missing creds and pin role/warehouse/db/schema to
  the terraform-created objects. RAW.TRIALS schema migrations:
  scripts/recreate_raw_trials.sh (drop + recreate + re-load; README
  Cloud section has the sequence).
- `make rag-build` — embed mart_trial_documents into Chroma
  (data/chroma/). Incremental by content_hash: no-change re-run embeds
  0 documents; FULL=1 rebuilds. Downloads the pinned embedding model on
  first run (local only — never CI).
- `make ask Q="..."` — cited Claude answer over the store (optional
  STATUS=/PHASE=/K=). Needs ANTHROPIC_API_KEY in the env; JSON out.
- `make eval` — score rag/eval/golden_questions.yml: retrieval
  hit-rate ≥ 0.8 and citation correctness ≥ 0.7 or non-zero exit.
  RETRIEVAL_ONLY=1 runs just the free deterministic half.
- `make verify-parity` — staging row count + completeness mart must be
  value-identical across duckdb and snowflake; non-zero on mismatch.
- `make dag-verify` — DAG integrity without Docker (DagBag import,
  task ids/edges, schedule, trigger rules, retry policy). Installs
  airflow/requirements-dagtest.txt into the venv first (the only path
  that installs apache-airflow).
- `make lint` — ruff + sqlfluff via pre-commit run --all-files

Canonical change-detection order from a clean state (any other order can
baseline the snapshot early and corrupt the day-0 demo — see the
2026-08-14 make-snapshot DECISIONS.md entry):
`make reset && make snapshot-day0 && make snapshot && make dbt && make verify-idempotent`

## Data source facts (verified against live API 2026-08-14 — empirical findings supersede docs)

- Endpoint: `https://clinicaltrials.gov/api/v2/studies`, no auth.
- Params: `query.cond="Atopic Dermatitis"`, `pageSize` (≤1000), `pageToken`
  cursor pagination, `filter.overallStatus`, `filter.phase`.
- Payload nests under `protocolSection`. Modules seen in captured fixtures:
  identificationModule*, statusModule*, sponsorCollaboratorsModule*,
  conditionsModule*, designModule*, armsInterventionsModule*,
  descriptionModule, eligibilityModule, oversightModule, outcomesModule,
  contactsLocationsModule, ipdSharingStatementModule, referencesModule
  (* = currently read by the parser); `resultsSection` only for some trials.
- Known quirks that MUST be handled: (1) array fields (conditions,
  interventions, locations) may be null/missing/empty — always default to []
  (locations not currently extracted);
  (2) dates are ISO strings at two precisions with no API-side
  normalization: "YYYY-MM-DD" (day) and "YYYY-MM" (month) — measured
  2026-08-14 across 1,738 AD studies (e.g. startDateStruct.date:
  1,188 day / 541 month). Date structs can also be absent entirely.
  Parse both precisions (month resolves to first-of-month,
  date_precision="month"); absent → None/None; any OTHER format →
  keep raw string, date_precision=None, log a warning, never raise;
  (3) `whyStopped` free-text exists only on some withdrawn/terminated trials.

## Determinism policy (core design principle)

AI sits at the edges; everything in the middle is deterministic.
- Anything computable is computed in SQL/Python, never asked of an LLM:
  status changes, counts, completeness %, date math, filters, joins.
- The LLM (Claude API) is used ONLY to synthesize prose over retrieved
  context. It never generates facts. Calls use temperature 0, a pinned
  model version, and a system prompt requiring NCT citations and an
  explicit "the context does not contain this" refusal when retrieval
  is insufficient.
- Embeddings: pinned model name + version in one constants file.
  Same input corpus must produce the same vector store.
- Same inputs → same outputs everywhere else: pinned dependency versions,
  date-partitioned idempotent ingestion, dbt runs reproducible per target.
- Test question for any design choice: "could this step give a different
  answer on a re-run?" If yes, justify it in DECISIONS.md or fix it.

## Engineering contracts

- Schema contract: every dbt model gets a schema.yml (columns, types,
  descriptions, tests) written BEFORE or WITH the SQL — never after.
- CLI contract: rag/query_llm.py has a defined interface — args in,
  structured output (answer + list of cited NCT IDs) out, non-zero exit
  on retrieval failure. Define it in the spec before implementing.
- Caching/idempotency: raw landing partitioned by ingest date (re-runs
  overwrite their own partition only); embeddings rebuilt incrementally
  for changed records, full rebuild only via explicit flag.
- Minimal but scalable: simplest standard solution now; the scaling path
  is a DECISIONS.md note, not speculative code.

## Communication style (applies to chat replies, comments, docs, commits)

- Result first: lead with what changed / passed / failed, then details.
- Plain English, short sentences. No task restatement, no "I will now..."
  preambles, no closing summaries that repeat the middle.
- If it fits in one sentence, one sentence. Explanations max 4 sentences
  (Teaching-rule explanations included).
- Ban filler adjectives: "robust", "comprehensive", "production-ready",
  "seamless", "powerful". Show the property; don't claim it.
- Code comments only where the code can't say it (a quirk, a why).
  Docstrings: one line unless the function has non-obvious behavior.
- Reports after a task: files touched, commands run, result, open risks,
  next step. Nothing else.
  
## Conventions

- Python 3.11+. Type hints everywhere. Parsing functions stay PURE
  (dict in, typed record out) — only the parquet bridge and the tests
  import them; everything downstream (dbt, the RAG embedder) reads the
  bridge's output, never the parser (F8(4) correction: the seeds are
  hand-written CSVs and the embedder reads mart_trial_documents).
- Dependencies: ask before adding ANY new package. Current allowlist:
  requests, pytest, dbt-core, dbt-duckdb, dbt-snowflake, pyarrow,
  duckdb, pyyaml, sentence-transformers, chromadb, anthropic, ruff,
  sqlfluff, pre-commit, sqlfluff-templater-dbt. Plus apache-airflow,
  test-only and isolated by owner ruling: pinned in
  airflow/requirements-dagtest.txt, installed only by make dag-verify
  (and CI's dag-verify job) — never in requirements.txt or make setup.
- dbt naming: `stg_` staging, `mart_` marts, snapshots in `snapshots/`.
  SQL keywords lowercase, one column per line in select lists.
- Secrets defense in depth: never commit .env, data/, *.duckdb, .terraform/,
  or credentials of any kind; never echo secrets into files, logs, or command
  output. Enforced in layers: .gitignore, the user-level block-secrets hook
  (blocks secret-looking Write/Edit content; Bash output is not covered), and
  the security-reviewer agent, which MUST run and pass before committing
  changes that touch terraform/, CI workflows, .env/credential handling,
  ingest network code, or LLM-context assembly (see Project tooling).
  Pre-push audits are two-layer: `scripts/secrets_audit.sh` (deterministic
  floor; run by a local pre-push hook and in CI on pushes to main and on
  pull requests) runs first, then the security-reviewer's judgment on top.

## Teaching rule (IMPORTANT)

The developer is learning dbt and Airflow. The first time any concept from
these tools appears in a session (e.g. snapshot strategies, ref(), sources,
materializations, DAG task dependencies, idempotency patterns), add a
2-4 sentence plain-language explanation of what it is and why it's used
here, BEFORE the implementation. Every line merged must be explainable by
the developer in a job interview. Prefer the simple, standard way over the
clever way.

## Workflow rules

- Agent-loop tasks: the spec in `specs/` is the contract. Its DONE command
  is the only definition of done. Do not weaken failing tests. If a spec or
  fixture seems wrong, STOP and report — never silently repair.
- Fixtures in tests/fixtures/ are captured from the live API: read-only.
- Security-reviewer should-fixes may exceed a spec's touch-list;
  deviation disclosed, never silent.
- Commit at every green state with a descriptive message.
- End each loop with a summary: what changed + decisions the spec didn't
  cover, listed explicitly for human review.
- Live network calls: only via `make ingest`, the cloud targets
  (`make s3-sync` / `load-snowflake` / `dbt-snowflake` /
  `verify-parity`, terraform), `make rag-build` (Hugging Face fetch of
  the pinned embedding model), `make ask` / `make eval` (Claude API),
  and the local Airflow DAG (which wraps those same targets in
  Docker) — never inside pytest or CI.

## Project tooling

Index only — hooks fire from the developer's local, gitignored
.claude/settings.local.json (wiring is local-only by design; see the
run-tests entry); agents and skills self-describe in their own files. All agents are report-only by contract: none carry
Write/Edit, and their instructions forbid fixing, committing, or working
around findings (Bash is granted for git/pytest, so the boundary is
prompt-enforced, not a permission wall). A finding is fixed in the main
session or explicitly accepted — never auto-fixed, ignored, or committed
around.

- `run-tests` hook — `.claude/hooks/run-tests.py` (committed); after any .py
  edit inside this repo, runs pytest and blocks on red. The WIRING is
  local-only by design (phase-7 ruling, DECISIONS.md): a committed
  settings.json would auto-execute an inbound PR branch's hook + pytest +
  conftest.py for anyone opening it in Claude Code. One-time re-enable —
  copy this block into the gitignored `.claude/settings.local.json`:
  `{"hooks": {"PostToolUse": [{"matcher": "Write|Edit|MultiEdit|NotebookEdit",
  "hooks": [{"type": "command", "command": "python3
  \"$CLAUDE_PROJECT_DIR/.claude/hooks/run-tests.py\""}]}]}}`.
  Surviving surface no config closes: running pytest on an inbound branch
  still executes that branch's conftest.py — review conftest.py and
  test-file changes in the GitHub UI before running pytest on it.
- `block-secrets` hook — `~/.claude/hooks/block-secrets.py` (user-level, all
  projects); blocks writes containing secret-looking values.
- `code-reviewer` agent — `.claude/agents/`; diff review against this file's
  conventions. Run at each spec's finish line, before commit.
- `security-reviewer` agent — `.claude/agents/`; secrets/exposure/prompt-
  injection review. Mandatory-use rule: see "Secrets defense in depth" under
  Conventions.
- `functionality-tester` agent — `.claude/agents/`; runs the suite + the
  spec's DONE command, compares behavior to intent. Run after code-reviewer.
- `coherence-auditor` agent — `.claude/agents/`; whole-repo drift audit vs
  CLAUDE.md/PLAN.md/DECISIONS.md. MANDATORY once at each PLAN.md phase exit.
- `/selfcheck` command — `.claude/commands/selfcheck.md`; verifies the last
  commit (suite, DONE command, determinism, fixtures), then stops.
- `strategic-compact` skill — `~/.claude/skills/strategic-compact/`
  (user-level); suggests /compact at phase breakpoints.

## Current status

- Phase 6 complete locally (2026-08-15): the daily DAG
  trial_safety_pipeline (Astro Runtime 3.3-2, local Docker) runs
  ingest → parse → circuit breaker → local dbt (live snapshot +
  build) → RAG reindex, then cloud load → snowflake build → parity
  (local-first post-phase-6 ruling: a cloud outage must never cost a
  snapshot day), all 11 tasks green on two same-day triggers with the
  second an end-to-end no-op (recorded runs predate the reorder). R1 (hard
  deletes live-only + circuit breaker) and R2 (delete-by-partition +
  scoped COPY FORCE) landed. make dag-verify covers DAG integrity
  without Docker (own CI job). Demo capture pending after merge
  (docs/demo_checklist.md). Next is Phase 7 (packaging). See PLAN.md.
- Snowflake trial active; creds live only in .env (never committed).
  Terraform state is local and gitignored. ANTHROPIC_API_KEY: env/.env
  only, never CI.

(Update this section at the end of every working day.)
