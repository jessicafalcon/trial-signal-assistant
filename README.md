# Trial & Safety Signal Assistant

**What happens to a clinical trial after it is registered, and why do
some of them stop?**

This repository answers that question for one disease, atopic
dermatitis, using only public data. A daily pipeline pulls every
registered trial from ClinicalTrials.gov, keeps a dated history of each
trial's status, and lets anyone ask plain-English questions such as
*"why was the tezepelumab trial stopped?"* The answer comes back in a
sentence or two, with the registry's own trial IDs cited as evidence.

It is a small, complete version of a pattern large clinical-development
organisations are building right now: one governed data platform plus
an AI assistant, so trial teams ask a question instead of hunting
through dashboards. Everything that can be computed is computed. The AI
only writes prose over facts the pipeline has already retrieved, and it
never invents one.

---

## Contents

**For everyone**
1. [The problem](#1-the-problem)
2. [The idea](#2-the-idea)
3. [How it works, step by step](#3-how-it-works-step-by-step)
4. [See it work](#4-see-it-work)
5. [The data](#5-the-data)
6. [What the evidence shows](#6-what-the-evidence-shows)
7. [Design choices worth knowing](#7-design-choices-worth-knowing)
8. [How it was built](#8-how-it-was-built)
9. [Limits, honestly](#9-limits-honestly)
10. [Conclusion](#10-conclusion)
11. [Next steps](#11-next-steps)
12. [Glossary](#12-glossary)

**For engineers**
13. [Setup](#13-setup)
14. [Run it](#14-run-it)
15. [Cloud target (S3 + Snowflake)](#15-cloud-target-s3--snowflake)
16. [Repository map and further reading](#16-repository-map-and-further-reading)

---

## 1. The problem

ClinicalTrials.gov is the public registry of clinical studies. For a
single active disease area it holds thousands of records, each with a
status (recruiting, completed, terminated, withdrawn, and so on), a
sponsor, a phase, and often a free-text explanation of why a study
stopped.

Three things make that registry hard to use as a decision tool.

- **It only shows today.** The registry tells you a trial is
  terminated. It does not tell you when it flipped from recruiting to
  terminated, or what it looked like last month. Cycle time, the
  metric a development organisation cares about most, is invisible.
- **The interesting facts are buried in prose.** "Why did it stop?" is
  answered in a free-text field on some records, in whatever words the
  sponsor chose. It cannot be filtered or counted without reading.
- **Asking an AI directly is not safe.** A general chatbot will answer
  "why was this trial withdrawn?" fluently and sometimes wrongly. In a
  regulated setting an answer without a verifiable source is worse than
  no answer.

The question this project set out to answer: can a small team build
something that records the history, answers the prose questions, and
never says anything it cannot cite?

## 2. The idea

One rule shapes the whole design: **AI sits at the edges, everything in
the middle is deterministic.**

- Fetching, cleaning, counting, comparing dates, detecting a status
  change: all of this is ordinary code and SQL. Run it twice on the same
  input and you get the same output, byte for byte.
- The language model (Claude) is used for one job only: turning a
  handful of retrieved registry passages into a readable answer. It is
  told which passages it may use, it must cite the trial ID for every
  claim, and if the passages do not contain the answer it must say so.
- Every citation is checked by code after the model answers. An ID the
  model mentions that was not in the retrieved passages is quarantined,
  not shown as evidence.

The payoff is an assistant whose every sentence can be traced back to a
registry record, and a data platform whose every number can be
recomputed.

## 3. How it works, step by step

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
dbt: staging ──► snapshots (SCD2 on overall_status; both targets) ──► marts
        │
        ▼
Embeddings (sentence-transformers, per-field docs) ──► Chroma (+ metadata)
        │
        ▼
RAG retrieval ──► Claude API ──► grounded answer with NCT citations
```

In plain terms, once a day:

1. **Fetch.** Download every atopic dermatitis study from the public
   API (about 1,700 records) and save the raw files under today's date.
   Re-running the same day overwrites the same folder, so nothing
   duplicates.
2. **Parse.** Turn the nested API records into one flat, typed row per
   trial: ID, title, status, phase, sponsor, conditions, interventions,
   start date, why it stopped, summaries. The parser handles the
   registry's known quirks (dates that are sometimes only "year-month",
   lists that are sometimes missing) and is covered by tests against
   real captured payloads.
3. **Safety check.** If today's file holds fewer than 80% of
   yesterday's rows, stop. A half-empty download must not be mistaken
   for a thousand trials being delisted.
4. **Model.** dbt builds the tables. Staging tables type the raw data.
   A snapshot compares today's status for each trial with the last
   recorded one and writes a new history row only when it changed.
   Marts derive the useful views: status transitions, field
   completeness per day, ingest history, and the text corpus for the
   assistant.
5. **Index.** Each trial's summary, description, and stop reason
   becomes a searchable document. Only documents whose content changed
   are re-embedded.
6. **Ship to the cloud.** The same parsed files sync to S3 and load into
   Snowflake, where the same dbt project builds the same tables. A
   parity check confirms both warehouses agree.
7. **Answer.** When someone asks a question, the most relevant
   documents are retrieved, Claude writes an answer over them, and code
   verifies the citations before the answer is returned.

Airflow runs steps 1 to 6 as one scheduled job. Local steps run before
cloud steps, so a cloud outage can never cost a day of history.

![Airflow graph view: all 11 tasks green](docs/assets/pipeline-graph.png)

*One daily run, end to end: ingest → parse → circuit breaker → local
dbt (live snapshot + build) → RAG reindex, then S3 sync → Snowflake
load → Snowflake build → cross-target parity check.*

## 4. See it work

Ask a question:

```
$ make ask Q="Why was the tezepelumab monotherapy trial in atopic dermatitis stopped?"
{
  "answer": "The tezepelumab monotherapy trial in atopic dermatitis was
             stopped because tezepelumab as a monotherapy in atopic
             dermatitis did not reach the targeted efficacy level
             pre-established for this patient population [NCT03809663].",
  "cited_nct_ids": ["NCT03809663"],
  "unverified_nct_ids": [],
  "retrieved_ids": [
    "NCT03809663:why_stopped",
    "NCT03809663:brief_summary",
    "NCT00757042:brief_summary",
    "NCT06174493:brief_summary",
    "NCT02347176:brief_summary"
  ],
  "model": "claude-sonnet-4-5-20250929"
}
```

Read it like this: five passages were retrieved, the model used one
trial and cited it, and the `unverified_nct_ids` list is empty because
it did not mention any trial it had not been shown. The wording of the
reason is the sponsor's own text from the registry.

The assistant is scored against a hand-curated set of ten questions
(`make eval`): five "why did it stop" questions, two drug lookups, two
filtered questions, and one question whose correct answer is a refusal.

```
question                           retrieval  citation
q01_tezepelumab_why_stopped        PASS       PASS
q02_lack_of_efficacy_interim       PASS       PASS
q03_slow_enrollment                PASS       PASS
q04_safety_reasons                 PASS       PASS
q05_crisaborole_business           PASS       PASS
q06_barzolvolimab_lookup           PASS       PASS
q07_lebrikizumab_lookup            PASS       PASS
q08_phase2_futility_filtered       PASS       PASS
q09_withdrawn_business_filtered    PASS       PASS
q10_refusal_budget                 n/a        PASS

retrieval hit-rate: 1.00 over 9 questions (threshold 0.8; refusal question excluded)
citation correctness: 1.00 over 10 questions (threshold 0.7)
```

The refusal question matters as much as the other nine. Asked something
the registry cannot answer, the model must say "the context does not
contain this" rather than improvise. It does.

A recording of a full scheduled run, trigger to all-green, is in
[docs/assets/pipeline-run.gif](docs/assets/pipeline-run.gif).

## 5. The data

All figures below are computed by SQL over the latest local partition
(2026-08-17) unless stated otherwise. The registry holds 1,738 atopic
dermatitis studies.

**Where the trials stand today**

| Status | Trials |
|---|---:|
| Completed | 1,033 |
| Recruiting | 184 |
| Unknown (not verified by the sponsor in over two years) | 169 |
| Terminated | 118 |
| Active, not recruiting | 91 |
| Not yet recruiting | 68 |
| Withdrawn | 54 |
| Enrolling by invitation | 17 |
| Other | 4 |

**Why trials stop.** 172 trials are terminated or withdrawn. 161 of
them (93.6%) give a reason in the registry. A rough keyword grouping of
those reasons, for orientation only:

| Reason (keyword bucket) | Trials |
|---|---:|
| Business, sponsor, or funding decision | 44 |
| Slow or low enrollment | 39 |
| Lack of efficacy or futility | 22 |
| Safety finding | 5 |
| COVID-19 | 4 |
| Other or unclassified | 48 |

This is the corpus the assistant answers "why" questions over. Every
one of those 161 sentences is a searchable, citable document.

**Who runs the trials.** Pfizer (54), LEO Pharma (48), NIAID (40),
Sanofi (36), AbbVie (31), Regeneron (31), and Eli Lilly (29) lead the
sponsor list. Sponsor is a filter, not a search term (see Limits).

**How complete the data is.** One row per day, so data quality is a
time series, not a snapshot:

| Measure | Value |
|---|---:|
| Trials with posted results | 20.9% |
| Stopped trials with a stated reason | 93.6% |
| Start dates given to the day | 68.4% |
| Start dates given to the month only | 31.1% |
| Start date absent | 0.5% |

**The searchable corpus.** 2,865 documents: 1,738 brief summaries, 965
detailed descriptions, and 162 stop reasons. Each is indexed separately
so a stop reason is retrieved as a stop reason, not diluted inside a
long description.

**Status history.** Real registry statuses change slowly, over months.
To show the change-detection layer working on day one, four real trials
are seeded with a labelled, synthetic "yesterday" status. The history
table therefore holds 1,742 rows (1,738 live plus 4 seeded), and the
transitions mart shows exactly four transitions, each marked with its
origin:

| Trial | From | To | Origin |
|---|---|---|---|
| NCT00001760 | Active, not recruiting | Completed | seed → live |
| NCT00124709 | Recruiting | Terminated | seed → live |
| NCT00177268 | Not yet recruiting | Recruiting | seed → live |
| NCT00568997 | Recruiting | Active, not recruiting | seed → live |

Every transition detected after these four is a real change in the
registry. The origin column keeps seeded and live history apart, so the
demo never passes synthetic data off as real.

## 6. What the evidence shows

Every claim here is one command or one committed capture.

- **Both warehouses agree.** The same dbt project builds on DuckDB and
  Snowflake. `make verify-parity` fails unless row counts, the full
  completeness mart, and the status-transition values are identical on
  both. Captured: [verify-parity.txt](docs/assets/verify-parity.txt),
  5,214 rows and byte-equal mart output on both engines, with
  [the same count in Snowsight](docs/assets/snowsight-row-count.png)
  queried as the pipeline's least-privilege role.
- **Re-running changes nothing.** Re-taking the status snapshot on
  unchanged data adds zero rows and leaves the table fingerprint
  identical: [verify-idempotent.txt](docs/assets/verify-idempotent.txt).
  Re-running the embedding step with no mart changes embeds 0
  documents. A same-day re-trigger of the whole scheduled run is an
  end-to-end no-op.
- **The cloud is reproducible.** Terraform owns the S3 bucket, the IAM
  trust handshake, and the Snowflake objects. After the demo ran,
  [terraform plan reports "No changes"](docs/assets/terraform-plan.txt).
  Each daily partition loads 1,738 of 1,738 rows
  ([database tree](docs/assets/snowsight-schemas.png)).
- **It is cheap.** The entire project to date, every load, build, and
  parity check, cost
  [$2.25 of Snowflake trial credits](docs/assets/snowsight-cost.png) on
  an X-Small warehouse that suspends after 60 seconds idle.
- **It is tested.** 120 tests run without network access: the parser
  against captured real payloads, the guards, the DAG's structure. dbt
  adds 63 data tests on the tables themselves.
- **It fails safe.** The 80% circuit breaker stops the run before the
  snapshot can misread a collapsed download as mass delisting. Missing
  cloud credentials skip the cloud task group (variable names logged,
  never values) while the local pipeline completes.

## 7. Design choices worth knowing

Each of these has a longer entry in [DECISIONS.md](DECISIONS.md).

- **Two warehouses, one project.** DuckDB is a single local file and
  costs nothing, so it is the development and CI target. Snowflake is
  what the industry runs on, so it is the demo target. The same SQL
  builds on both, and the parity check is the proof.
- **History by snapshot, not by re-fetching.** A dbt snapshot records a
  new row only when a trial's status changes. That gives a compact,
  queryable history of every trial without storing 1,738 copies a day.
- **A labelled synthetic day zero.** Waiting months for the registry to
  change would leave the change-detection layer unprovable. Seeding
  four plausible predecessor statuses, visibly labelled as synthetic all
  the way into the mart, lets the mechanism be demonstrated on day one
  without ever passing off synthetic data as real.
- **Citations are verified, not trusted.** The model's cited IDs are
  intersected with what retrieval returned. Anything else is quarantined
  in a separate list. A hallucinated citation cannot reach the answer.
- **Pinned everything.** Dependency versions, the embedding model, the
  Claude model ID, and temperature 0. Same corpus, same vector store,
  same answer.
- **Deliberately thin orchestration.** Every Airflow task calls a make
  target, so each step has exactly one definition that runs identically
  with or without Airflow, and the DAG's structure is tested without
  Docker.

## 8. How it was built

Spec-driven agent loops with human gates. Each of the seven phases is a
written spec (`specs/`) with one DONE command as the only definition of
done. A coding agent (Claude Code) executed the mechanical loop: write
the schema contract with the model, keep the parser pure, commit at
every green state. Judgment stayed human: every push, every terraform
apply, every audit ruling, and every piece of narrative prose crossed a
human gate. Review agents (code, security, functionality, coherence)
reported findings; nothing was fixed without an explicit per-finding
ruling, and the rulings are logged. DECISIONS.md records every
non-obvious choice as a why-not-X entry, including the ones that
superseded earlier decisions.

Security is layered and mostly deterministic: `.gitignore`, a
write-blocking hook, and a seven-check mechanical floor
(`scripts/secrets_audit.sh`) run before any judgment review. CI re-runs
both gitleaks and the floor script from the base branch's copies on
every pull request, so a change to the checks can never mask its own
diff. When four rounds of pre-push audit converged, the owner closed
it as a risk decision and parked the residuals as a pre-public
checklist, every item of which was cleared or explicitly re-accepted
before the repository went public.

The workflow and the pipeline follow the same principle: determinism
where possible, logged human judgment where not.

## 9. Limits, honestly

What changes at scale, and what this build does not do.

- **Retrieval.** The small embedding model (all-MiniLM-L6-v2, top 5)
  misses rare drug names, and sponsors are filterable metadata, not
  semantically searchable: "the Celldex trial" needs an exact filter.
  Production wants hybrid search or a reranker. On this stack,
  Snowflake Cortex Search would replace the local embedding path and
  bring retrieval inside the warehouse's access-control and lineage
  boundary, which the local vector store lacks.
- **Phase filtering is exact-string.** `PHASE2` does not match
  `PHASE1/PHASE2`. Decomposed phase values are the fix if this grew.
- **Auth.** Password auth in `.env` is trial-account posture. Real
  deployments use key-pair auth, a secrets manager, and separate loader
  and transformer roles.
- **Loading.** The partition-scoped delete-and-reload is a deliberate
  trade against Snowpipe: at 1,738 rows a day it buys deterministic,
  replayable loads. At real volume the default flips to Snowpipe off S3
  events, with this path kept for backfill.
- **Two snapshot histories is a demo pattern.** Each warehouse keeps
  its own history and parity proves they agree, so the demo survives
  either target alone. Production runs one authoritative history on the
  warehouse.
- **The circuit breaker has declared blind spots.** It compares only
  the latest partition to its immediate prior at a fixed 80%. An 86%
  single-day truncation, a slow multi-day drift, and an empty latest
  partition all pass (the empty case is caught downstream). Production
  wants an absolute floor plus drift alerting.
- **Orchestration is clock-driven.** At scale: Airflow assets so
  downstream tasks trigger on data landing, Cosmos to expand the dbt
  graph into per-model tasks, deferrable S3 sensors, and a managed
  deployment with alerting. Today the DAG runs only in local Docker.
- **State and drift.** Terraform state is a local file; a team needs a
  remote backend with locking. Ingestion re-fetches the full corpus
  daily; at scale it becomes an incremental fetch on the registry's
  last-update date. Parity runs only when a human runs it, because CI
  holds no cloud credentials by design.

## 10. Conclusion

A registry that only shows today can be turned into a history, and a
language model can be made to answer questions over it without ever
inventing a fact. Neither required exotic technology. It required
drawing one line clearly, between what is computed and what is written,
and then proving on every run that the computed side is identical and
the written side is cited.

The result is a pipeline where every number is recomputable, every
answer is traceable to a registry record, both warehouses provably
agree, and the whole thing cost a few dollars to run. That is the shape
of a trial-signal platform, at a scale one person can hold in their
head.

## 11. Next steps

Parked items with their reasoning live in [docs/BACKLOG.md](docs/BACKLOG.md).
In rough priority order:

1. **Surface delisted trials.** Trials that vanish from the registry are
   already recorded as closed history rows, but no mart or document
   shows them yet.
2. **Better retrieval.** Hybrid search or reranking for rare drug
   tokens, and semantically searchable sponsor names. On Snowflake, the
   converging path is Cortex Search over the document mart.
3. **Richer phase matching.** Decomposed phase values with set
   membership instead of exact-string filters.
4. **Data-aware scheduling.** Airflow assets, Cosmos, deferrable
   sensors, and a managed deployment with alerting.
5. **One authoritative history.** Collapse the dual-snapshot demo
   pattern onto the warehouse and demote DuckDB to a dev target.
6. **Operational hardening.** Scheduled parity with scoped read-only
   credentials, a remote Terraform backend with locking, incremental
   ingestion, and an absolute-count floor on the circuit breaker.

## 12. Glossary

- **ClinicalTrials.gov / NCT ID.** The US public registry of clinical
  studies, and the unique identifier each study gets (e.g.
  NCT03809663). Citations in this project are NCT IDs.
- **Atopic dermatitis.** Chronic eczema. Chosen because it is a dense,
  active immunology area with a rich history of stopped trials.
- **Partition.** One day's download, stored under its date. Re-running a
  day overwrites only that day.
- **dbt.** A tool that builds warehouse tables from versioned SQL and
  tests them. **Staging** tables clean and type raw data; **marts** are
  the derived tables people query.
- **Snapshot (SCD2).** A dbt feature that records a new row for a record
  only when a watched field changes, with valid-from and valid-to
  dates. It is how this project keeps status history.
- **DuckDB / Snowflake.** Two SQL warehouses. DuckDB is a free
  single-file engine used for development and CI; Snowflake is the
  cloud warehouse used for the demo.
- **Airflow / DAG.** A scheduler and the definition of a job as ordered
  tasks (a directed acyclic graph). The DAG here has 11 tasks.
- **Embedding / vector store.** A numeric representation of a text
  passage that lets similar passages be found by meaning. Stored in
  Chroma, a local vector database.
- **RAG (retrieval-augmented generation).** Retrieve relevant passages
  first, then have the language model write over them only.
- **Circuit breaker.** A check that stops the run when today's download
  is suspiciously smaller than yesterday's.
- **Parity.** Proof that two warehouses hold identical results for the
  same inputs.
- **Terraform.** Code that creates and tracks cloud resources so they
  can be recreated identically.

---

## 13. Setup

Prerequisites: Python 3.11 for the venv, the reference version matching
CI (3.12/3.13 acceptable; 3.14 unsupported: `make dag-verify` installs
apache-airflow under Airflow's published constraints, which exist for
3.11–3.13 only), and [gitleaks](https://github.com/gitleaks/gitleaks)
(`brew install gitleaks`) for the secrets audit. For the cloud target
only: the aws CLI and
[terraform](https://developer.hashicorp.com/terraform). `make setup`
warns when any of the three is missing.

    make setup   # venv, dependencies, pre-commit hooks
    make test    # parser + guard suite (no network)

Troubleshooting `make dag-verify`: if pip fails during the constraints
install with "Cannot uninstall … no RECORD file" and `site-packages`
holds two dist-info directories for one package, delete that package's
remnants from `.venv/lib/python3.11/site-packages/` and reinstall the
pinned version. Do not use `pip install --ignore-installed`; it worsens
the state (observed 2026-08-15 with `more_itertools`).

## 14. Run it

Local, from a clean state. This order matters: any other order can
baseline the snapshot early (see DECISIONS.md).

    make ingest            # live fetch → data/raw/ (network)
    make parse             # parser → data/parsed/ parquet
    make reset             # clean local warehouse
    make snapshot-day0     # seed + snapshot the labeled synthetic day-0 state
    make snapshot          # circuit breaker, then live snapshot
    make dbt               # dbt build (models + snapshot + tests)
    make verify-idempotent # prove the snapshot re-run is a no-op
    make rag-build         # embed mart_trial_documents into Chroma
    make ask Q="..."       # cited answer (needs ANTHROPIC_API_KEY)
    make eval              # golden-question scoring

On a schedule, the same targets run as one daily Airflow DAG (local
Docker via the Astro CLI; Airflow never runs in CI):

    set -a; source .env; set +a   # cloud credentials for the containers (optional)
    cd airflow && astro dev start # builds the image, prints the UI URL
    # UI: unpause trial_safety_pipeline, Trigger. astro dev stop when done.

The DAG passes exactly four env vars into the containers
(`SNOWFLAKE_ACCOUNT/USER/PASSWORD`, `AWS_PROFILE`), hence the `source
.env`, and mounts `~/.aws` read-only. Without them everything still runs
and the cloud group skips. `snapshot-day0` is deliberately not a DAG
task: it is a one-time bootstrap whose re-run would corrupt the demo
transitions.

## 15. Cloud target (S3 + Snowflake)

One-time provisioning is a single converging `terraform apply`
(sequence and provider caveats in
[terraform/README.md](terraform/README.md)). Then:

    make s3-sync                  # parsed parquet → s3://<bucket>/parsed/
    make load-snowflake           # per-partition: delete its rows, COPY its files with FORCE
    make snapshot-day0-snowflake  # ONE-TIME: seed + snapshot the labeled day-0 state
    make snapshot-snowflake       # breaker-guarded live snapshot (daily; the DAG's job)
    make dbt-snowflake            # dbt build --target snowflake
    make verify-parity            # cross-target compare: rows, completeness, transitions

Credentials live only in `.env` (see `.env.example`); the make targets
pin role/warehouse/database/schema to the terraform-created objects, so
the demo provably runs as `TRANSFORMER` on the X-Small warehouse
whatever the caller's environment says. Change detection (the day-0
seed, the SCD2 snapshot, and the status-change mart) runs on both
targets; each warehouse keeps its own snapshot history, and parity
compares the transition values, never the detection timestamps, which
are each warehouse's own run times. Only the RAG document mart stays
DuckDB-only: the embedder reads the local file.

Recovery paths. If Snowflake falls a partition behind (a day when the
cloud tasks skipped): `make load-snowflake ALL=1`. A diverged or
wrongly-baselined snapshot re-baselines via
`scripts/rebaseline_snowflake_snapshot.sh` (`CONFIRM_REBASELINE=1`
gate; intermediate history is not reconstructable; each destructive
gate answers to its own token). Schema migrations for RAW.TRIALS:
`scripts/recreate_raw_trials.sh` (drop + recreate + re-load; the data is
reproducible by design).

**Cost.** X-Small warehouse, 60-second auto-suspend, created suspended.
The S3 bucket is versioned with a 30-day expiry on noncurrent versions:
the DAG rewrites the same-day key on every same-day re-run, so old
versions would otherwise accrue per run and be retained forever.

**CI runs none of the cloud path.** The test job runs the suite without
airflow installed (the DAG tests skip there; the dedicated dag-verify
job installs it under Airflow's constraints file and runs them), the
terraform job is `fmt`/`validate` only, and AWS, Snowflake, and the
Claude API are never touched in CI. No cloud credential exists there.

## 16. Repository map and further reading

- `ingest/` API fetching and pure parsing functions, tested against
  captured payloads in `tests/fixtures/`.
- `dbt_project/` staging models, the status snapshot, marts, seeds,
  data tests, and the Snowflake load macro. Two targets in
  `profiles.yml`.
- `rag/` embedding build, query layer, and the golden-question eval.
- `airflow/` the Astro project and the daily DAG.
- `terraform/` S3 and Snowflake infrastructure.
- `scripts/` secrets audit, Snowflake load, parity check, and recovery
  scripts.
- `specs/` the seven phase specs, each with one DONE command.
- [DECISIONS.md](DECISIONS.md) every non-obvious choice as a why-not-X
  entry. [PLAN.md](PLAN.md) the phase history and pre-public audit
  trail. [docs/BACKLOG.md](docs/BACKLOG.md) parked work.
  [CLAUDE.md](CLAUDE.md) the working rules the coding agent followed.

**Status: complete.** All seven phases done and merged; the repository
is public.
