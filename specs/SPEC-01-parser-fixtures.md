# SPEC-01 — ClinicalTrials.gov Parser + Test Fixtures

> Agent-loop spec. Read this file fully before writing any code.
> The definition of done is the DONE COMMAND below — nothing else.

## Goal

Make `ingest/fetch_clinical_trials.py` correctly parse real Atopic Dermatitis
trial records from the ClinicalTrials.gov API v2, proven by a pytest suite
running against captured fixture payloads. No live network calls in tests.

## Context (do not re-derive this — it is verified)

- API: `https://clinicaltrials.gov/api/v2/studies`, no auth.
- Params in use: `query.cond="Atopic Dermatitis"`, `pageSize`, `pageToken`
  (cursor pagination), `filter.overallStatus`, `filter.phase`.
- Everything relevant nests under `protocolSection`
  (`identificationModule`, `statusModule`, `sponsorCollaboratorsModule`,
  `descriptionModule`, `designModule`, `outcomesModule`,
  `eligibilityModule`). `resultsSection` exists only for some trials.
- Known data quirks that MUST be handled, not worked around:
  1. Array fields (`conditions`, `interventions`, `locations`) can be
     null, missing, or empty.
  2. Dates are ISO strings at two precisions with no API-side
     normalization: `"YYYY-MM-DD"` (day) and `"YYYY-MM"` (month) —
     measured 2026-08-14 across 1,738 AD studies. Date structs can
     also be absent entirely. Any other format must be kept raw with
     `date_precision=None` and a logged warning, never an exception.
  3. Withdrawn trials may carry a free-text `whyStopped` field; most
     trials have no such field at all.

## Fixtures (already captured by the human — treat as read-only)

Located in `tests/fixtures/`. Do not edit, regenerate, or "fix" them —
they are ground truth captured from the live API:

- `fixture_complete.json` — a well-populated ACTIVE_NOT_RECRUITING Phase 2
  trial (barzolvolimab-type record) with all modules present.
- `fixture_withdrawn.json` — a WITHDRAWN trial with a `whyStopped` string.
- `fixture_sparse.json` — a record with null/missing array fields.
- `fixture_dates_mixed.json` — records covering ISO-day dates, ISO-month
  dates, and an absent date struct.
- `fixture_page.json` — a full paginated response envelope with
  `nextPageToken`, for testing pagination handling.

If a fixture appears malformed, STOP and report it — do not repair it.

## Deliverables

1. `ingest/fetch_clinical_trials.py` refactored so that:
   - Fetching (network) and parsing (pure functions) are separate, so the
     parser is testable without network.
   - `parse_study(study: dict) -> TrialRecord` returns a typed structure
     (dataclass or TypedDict) with at minimum: `nct_id`, `brief_title`,
     `overall_status`, `phase`, `sponsor_name`, `conditions` (list, never
     None), `interventions` (list, never None), `start_date_raw`,
     `start_date` (ISO date or None), `date_precision`
     (`"day" | "month" | None`), `why_stopped` (str or None),
     `has_results` (bool).
   - Date parsing handles both ISO precisions; month-precision dates
     resolve to the first of the month with `date_precision="month"`.
     Absent date struct → `start_date=None`, `date_precision=None`.
     Unknown format → keep `start_date_raw`, `start_date=None`,
     `date_precision=None`, log a warning, never raise.
   - Pagination follows `nextPageToken` until exhausted or a `max_pages`
     cap is hit.
   - `QUERY_PARAMS` targets Atopic Dermatitis (no diabetes placeholder).
2. `tests/test_parser.py` — pytest cases covering:
   - Full parse of `fixture_complete.json` with exact expected values.
   - Sparse record: arrays default to `[]`, no KeyError/AttributeError.
   - `"YYYY-MM-DD"` → ISO date + `date_precision="day"`; `"YYYY-MM"` →
     first-of-month + `date_precision="month"`; absent date struct →
     `None`/`None`; one unknown-format string → raw kept,
     `date_precision=None`, no exception.
   - `why_stopped` extracted when present, `None` when absent.
   - Pagination: envelope parsing yields the studies list + next token.
   - A raw fixture round-trip: every study in `fixture_page.json` parses
     without raising.
3. `Makefile` target `make test` running the DONE COMMAND.

## DONE COMMAND (the only definition of done)

    pytest tests/test_parser.py -v

All tests pass, zero skips, zero warnings-as-errors suppressions added.

## Constraints

- Touch only: `ingest/fetch_clinical_trials.py`, `tests/`, `Makefile`.
  Do not modify `dbt_project/`, `dags/`, `terraform/`, `rag/`, or fixtures.
- Dependencies: stdlib + `requests` + `pytest` only. No new packages
  (no pydantic, no dateutil) — date parsing is three known formats,
  write it explicitly.
- No live HTTP calls anywhere in the test suite.
- Do not weaken a failing test to make it pass. If a test seems wrong,
  stop and report the disagreement instead.
- Keep parsing functions pure (dict in, record out) — the dbt layer and
  the RAG embedder will both import them later.

## Out of scope (explicitly)

- Snowflake loading, S3 landing, dbt models, embeddings, Airflow wiring.
- openFDA ingestion.
- Retry/backoff sophistication beyond a simple timeout — this is a
  daily batch job, not a high-throughput client.

## Loop protocol

1. Read the current parser and all fixtures first.
2. Write the tests BEFORE refactoring the parser.
3. Run the DONE COMMAND after every change; iterate until green.
4. When green, run it once more from a clean shell, then summarize:
   what changed, any fixture surprises, any decisions made that the
   spec did not cover (list these explicitly for human review).
