# DECISIONS

Why-not-X log. One entry per non-obvious choice.

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
CLAUDE.md instead, where context can be given properly.

## 2026-08-14 — Dual dbt targets: DuckDB (local/CI) + Snowflake (demo)

DuckDB is the default target because it is a zero-cost, zero-setup local
file: contributors and CI can run `dbt build` with no credentials, no
network, and identical results per the determinism policy. Snowflake exists
as a second target purely to demonstrate the same models running on a real
cloud warehouse with COPY INTO from S3 — the pattern employers actually run.
Keeping both in one profiles.yml proves the dbt code is warehouse-portable
rather than coupled to one engine. CI stays green without Snowflake
credentials existing at all (the trial isn't even activated yet).
