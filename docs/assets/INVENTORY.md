# Demo asset inventory (captured 2026-08-15, post all-green DAG run)

Credit figure for the README: **$2.25 total org spend** (accumulated =
current month; entire project to date on the trial, XS warehouse,
60s auto-suspend).

| Asset | Shows | Cropped / redacted |
|---|---|---|
| pipeline-graph.png | Airflow graph view, all 11 tasks success, local-first fork-and-join with cloud TaskGroup expanded | Cropped from full-window shot to the graph band; no UI chrome captured |
| pipeline-run.gif | Timelapse of the same run: trigger → Running → all tasks green → Success badge (~7s, from a 35-frame screen recording) | Left nav rail cropped out (removed timezone chip); no URL bar recorded |
| snowsight-schemas.png | TRIAL_SIGNAL database tree: ANALYTICS (mart + staging views) and RAW (TRIALS, PARSED_TRIALS stage, PARQUET_FORMAT) | Nothing — captured without chrome |
| snowsight-row-count.png | Worksheet `select count(*) from trial_signal.raw.trials;` → 3,476 (2 partitions x 1,738) | Nothing removed. Note: context ribbon shows ACCOUNTADMIN / COMPUTE_WH (ad-hoc query context, not the pipeline's TRANSFORMER / TRIAL_SIGNAL_WH) |
| snowsight-warehouse.png | TRIAL_SIGNAL_WH details: X-Small, Auto suspend = 1 minute, auto-resume, activity after the run | Query-history user filter chip black-boxed (Snowflake username) |
| snowsight-cost.png | Cost Management org overview: $2.25 accumulated spend after the full run | Accounts Spend Summary table cropped off (contained the account locator) |
| ask-q1.txt | `make ask` Q1 full JSON: grounded answer, cited_nct_ids=[NCT03809663], empty unverified list, pinned model id | ANSI stripped; HF Hub / model-loading log lines removed |
| eval-summary.txt | `make eval` table: 10 golden questions, retrieval 1.00 (threshold 0.8), citation 1.00 (threshold 0.7) | ANSI stripped; HF Hub log lines and connector version warnings removed |
| verify-idempotent.txt | Snapshot re-run proof: row count + dbt_scd_id fingerprint identical before/after | ANSI stripped |
| verify-parity.txt | Cross-target parity: staging 3,476 on both engines; completeness mart identical for both partitions | ANSI stripped; connector version-warning lines removed (contained local paths) |
| terraform-plan.txt | `terraform plan` verdict: "No changes. Your infrastructure matches the configuration." | Verbatim excerpt of the owner-run plan output |

All images passed a leak inspection (no account locators, usernames,
URLs, emails, or local paths) and had embedded metadata stripped with
exiftool. Raw, unredacted originals stay in the gitignored demo/
directory and must never be committed.
