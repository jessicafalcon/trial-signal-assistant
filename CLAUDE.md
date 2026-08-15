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
S3 raw landing (JSON, partitioned by ingest date)   [Terraform, eu-west-3]
        │
        ├──► DuckDB  (local dev + CI target)
        └──► Snowflake (demo target, COPY INTO via external stage)
        │
        ▼
dbt: staging ──► snapshots (SCD2 on overall_status) ──► marts
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
- `rag/` — embedding build, query layer, `eval/` golden questions + scorer.
- `dags/` — Airflow DAG. `terraform/` — S3 + Snowflake infra.
- `data/` — gitignored. `data/raw/` JSON, `data/chroma/` vector store.
- `DECISIONS.md` — why-not-X log. Add an entry for every non-obvious choice.

## Commands (macOS, pip + venv)

- `make setup` — create .venv, pip install -r requirements.txt, pre-commit install
- `make test` — pytest (parser suite; no network calls allowed in tests)
- `make ingest` — live fetch AD trials → data/raw/ (network; never run in CI)
- `make dbt` — dbt build --target duckdb (default local/CI definition of green)
- `make dbt-snowflake` — dbt build --target snowflake (needs .env credentials)
- `make eval` — run rag/eval/run_eval.py against golden questions
- `make lint` — ruff + sqlfluff via pre-commit run --all-files

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
  (dict in, typed record out) — dbt seeds and the RAG embedder import them.
- Dependencies: ask before adding ANY new package. Current allowlist:
  requests, pytest, dbt-core, dbt-duckdb, dbt-snowflake, pyarrow,
  sentence-transformers, chromadb, anthropic, ruff, sqlfluff, pre-commit,
  sqlfluff-templater-dbt.
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
- Commit at every green state with a descriptive message.
- End each loop with a summary: what changed + decisions the spec didn't
  cover, listed explicitly for human review.
- Live network calls: only via `make ingest`, never inside pytest or CI.

## Project tooling

Index only — hooks fire from settings.json; agents and skills self-describe
in their own files. All agents are report-only by contract: none carry
Write/Edit, and their instructions forbid fixing, committing, or working
around findings (Bash is granted for git/pytest, so the boundary is
prompt-enforced, not a permission wall). A finding is fixed in the main
session or explicitly accepted — never auto-fixed, ignored, or committed
around.

- `run-tests` hook — `.claude/hooks/run-tests.py`; after any .py edit inside
  this repo, runs pytest and blocks on red. Wired in `.claude/settings.json`.
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

- Phase 3 complete locally (2026-08-14): SCD2 snapshot on overall_status,
  labeled synthetic day-0 seed, mart_trial_status_changes; DONE sequence
  + idempotency proof green on DuckDB from a clean state; CI green
  pending PR review. Next is Phase 4 (cloud: Terraform S3 + Snowflake).
  See PLAN.md for phases and exit criteria.
- Snowflake trial NOT yet activated. No Snowflake creds exist.

(Update this section at the end of every working day.)
