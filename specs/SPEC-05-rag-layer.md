# SPEC-05 — RAG layer: documents mart, embeddings, cited answers, eval

> Agent-loop spec. Read this, CLAUDE.md, and the F8/F11 entries in
> DECISIONS.md first. The DONE COMMAND is the only definition of done.
> ANTHROPIC_API_KEY exists only in the user's .env — never echo it,
> never let it near CI.

## Goal

Answer natural-language questions about trials with grounded, cited
Claude responses over a Chroma vector store — built deterministically
from a new documents mart, incrementally re-embeddable, and scored by
a committed eval. Resolves the four F8 requirements.

## Context (verified — do not re-derive)

- F8 requirements this spec must resolve: (1) embedder input surface,
  (2) incremental change key, (3) array-flattening rule for Chroma
  metadata, (4) CLAUDE.md's "dbt seeds ... import the parsers" comment
  is half-false and needs correcting.
- F11 warning: RAW.TRIALS DDL is a manual copy of the bridge SCHEMA;
  extending TrialRecord requires a live-table migration on Snowflake.
  This spec extends TrialRecord — the migration is in scope.
- TrialRecord today lacks the trial's descriptive text: descriptionModule
  (briefSummary, detailedDescription) is in the payload but unparsed.
  why_stopped is already extracted. 93.6% of withdrawn/terminated
  trials have why_stopped (161 of 172) — the "why" corpus is rich.
- Determinism policy: the LLM synthesizes prose over retrieved context
  ONLY; temperature 0; pinned model version; mandatory NCT citations;
  explicit refusal when context is insufficient. Embedding model pinned
  in one constants file.
- Engineering contracts: the query CLI has a defined interface before
  implementation. CI never has network or credentials: no model
  downloads, no API calls, no embedding in CI — unit tests use fakes.

## Deliverables

1. Parser extension: TrialRecord += brief_summary (str|None),
   detailed_description (str|None) from descriptionModule. Fixtures
   already contain these fields — extend tests from real fixture
   values. Bridge parquet schema grows the two columns; staging +
   schema.yml updated on both targets (divergence notes per F5
   pattern).
2. Snowflake migration (F11): documented, scripted path — recreate
   RAW.TRIALS from the updated DDL and re-run s3-sync + load after
   re-parse (data is reproducible by design; state the exact sequence
   in the summary and terraform/README or README Cloud section). Keep
   the DDL-is-a-copy cross-reference comments current.
3. `models/marts/mart_trial_documents.sql` (duckdb; excluded on
   snowflake like the snapshot — DECISIONS line): one row per
   (nct_id, doc_field) for doc_field in brief_summary,
   detailed_description, why_stopped where the text is non-empty.
   Columns: nct_id, doc_field, doc_text, overall_status, phase,
   sponsor_name, has_results, conditions_flat (F8 rule: arrays join
   with '; ' — record the rule in DECISIONS), content_hash
   (md5 of doc_text — the F8 incremental change key), ingest_date
   (latest partition only). schema.yml + tests: not_null everything,
   accepted_values doc_field, singular uniqueness test on
   (nct_id, doc_field).
4. `rag/constants.py`: embedding model name+revision pinned
   (sentence-transformers/all-MiniLM-L6-v2), Claude model id pinned,
   top_k, Chroma path (data/chroma/), collection name.
5. `rag/embed_and_store.py` + make rag-build: reads
   mart_trial_documents (dependency ruling: the duckdb python package
   is hereby APPROVED — pin it to the version dbt-duckdb already
   resolves, add to requirements.txt + allowlist in the same commit),
   embeds per-document, upserts to Chroma with id=nct_id:doc_field,
   metadata = the scalar columns + content_hash. Incremental: skip
   ids whose stored content_hash matches; --full rebuilds. Re-run
   with no changes embeds 0 documents (this is the idempotency
   check). Logs counts only, never doc text.
6. `rag/query_llm.py` + make ask Q="...": the CLI contract —
   args: question, optional --status/--phase metadata filters,
   --k override; retrieves top_k from Chroma (with filters), builds
   the context block (doc_text + nct_id labels), calls Claude
   (temperature 0, pinned model) with a system prompt requiring:
   answers grounded ONLY in context, every claim cites [NCTxxxxxxxx],
   and the exact sentence "The retrieved context does not contain
   this information." when it doesn't. Output: JSON to stdout —
   {answer, cited_nct_ids, retrieved_ids, model}. Exit non-zero on
   retrieval failure or empty store. No API key → clear error, exit 2.
7. Eval: `rag/eval/golden_questions.yml` (10 questions; see protocol —
   human curates) with per-question expected_nct_ids and
   expected_phrases. `rag/eval/run_eval.py` + make eval: for each
   question report (a) retrieval hit-rate — expected id in retrieved
   set (deterministic, no API), and (b) citation correctness — expected
   id in cited_nct_ids and expected_phrases present in the answer
   (one API call per question). Summary table + overall scores to
   stdout; exit non-zero below thresholds (retrieval ≥ 0.8,
   citation ≥ 0.7 — starting bars, tune in review). --retrieval-only
   flag for the free deterministic half.
8. Unit tests (CI-safe, no network): flattening rule, content_hash
   stability, incremental skip logic with a fake embedder, CLI
   context-block construction and refusal-sentence passthrough with a
   mocked API client. CI unchanged otherwise — no model downloads, no
   embedding, no API.
9. Docs: README "Ask questions" section (make rag-build / make ask /
   make eval, example Q&A with citation), CLAUDE.md: commands, repo
   map, and the F8(4) seeds-comment correction; PLAN phase 5; DECISIONS
   entries (flattening rule, change key, duckdb approval, snowflake
   doc-mart exclusion).

## DONE COMMAND (the only definition of done)

    make rag-build && make rag-build && make eval

where the second rag-build must report 0 documents embedded
(incremental idempotency), and make eval passes both thresholds.
Plus: full suite green, make dbt green, make dbt-snowflake green
after the migration, make lint green.

## Human gates (STOP points)

1. GOLDEN-SET CURATION: before writing golden_questions.yml, query
   the corpus for withdrawn/terminated trials with substantive
   why_stopped text (enrollment, safety, sponsor decision — not
   administrative registry withdrawals). Present the 15 best
   candidates (nct_id, status, one-line reason excerpt) plus 10 draft
   questions spanning: why-stopped (4-5), condition/intervention
   lookup (2-3), status/phase filtered (2), and one
   insufficient-context question whose correct answer is the refusal
   sentence. STOP for my selection/edits. My reply finalizes the yml.
2. FIRST PAID CALL: before the first real Claude API call, STOP and
   confirm the key is loaded and I approve spend (it's cents — the
   gate is about the boundary, not the amount).

## Constraints

- Touch only: ingest/, tests/, dbt_project/, rag/, Makefile, README,
  CLAUDE.md, PLAN.md, DECISIONS.md, requirements.txt, scripts/ (if
  the migration is scripted), .github/workflows/ci.yml (only if unit
  tests need wiring).
- Dependencies: duckdb approved per deliverable 5. chromadb,
  sentence-transformers, anthropic are already allowlisted — pin all
  three at install time. Nothing else without asking.
- Never log or print document text in build tooling (titles/ids/counts
  fine); answers obviously print doc-derived content — that's their
  job. Never print the API key or pass it as a CLI arg (env only).
- Teaching rule: embeddings/vector similarity, Chroma upsert
  semantics, metadata filtering, and RAG grounding each get their
  explanation at first use.

## Out of scope

- Airflow wiring of rag-build (Phase 6). Cortex Search, reranking,
  chunking beyond per-field docs, LLM-as-judge eval (README
  production-notes material). Locations extraction. Web UI.

## Loop protocol

1. Deliverables in order; parser extension first (it ripples), then
   the migration, then mart → embed → query → eval.
2. Human gate 1 before the yml; human gate 2 before the first API call.
3. DONE COMMAND after every change once the store exists.
4. When green: PLAN/CLAUDE status, single phase-5 commit ("phase 5:
   rag layer — documents mart, embeddings, cited answers, eval"),
   summary: eval score table verbatim, the migration sequence used,
   example make ask output, uncovered decisions. Do not push.
