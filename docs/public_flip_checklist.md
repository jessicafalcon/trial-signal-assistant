# Public flip checklist (human-only, in this order)

From SPEC-07's human gates, plus the phase-7 ruled additions. Execute
top to bottom; nothing here is automatable by design.

1. Rule the final whole-tree audit (SPEC-07 deliverable 4) and confirm
   `scripts/secrets_audit.sh` is green on main.
2. Apply the S3 lifecycle change if not yet applied:
   `terraform -chdir=terraform plan` (expect: 1 to add,
   aws_s3_bucket_lifecycle_configuration.raw_landing), then apply.
3. Merge the phase-7 PR into main; confirm all CI checks green.
4. Set the GitHub repo description and topics (drafts below).
5. Settings → Danger Zone → change visibility to Public.
6. IMMEDIATELY enable branch protection on main — require the lint,
   test, dbt, dag-verify, terraform, and secrets checks. This is not
   cosmetic: the CI self-governance guards (base-branch gitleaks
   config + base-branch floor script) run on pull requests only, so a
   direct push to main bypasses them. Branch protection is what closes
   that hole after the flip.
7. Add the repo link to CV/profile.

## Repo description draft

> Clinical trial data pipeline + RAG assistant: dbt on DuckDB/Snowflake,
> SCD2 status-change tracking, Airflow orchestration, and cited Claude
> answers over ClinicalTrials.gov data. Deterministic middle, AI at the
> edges.

## Topics draft

`dbt` · `snowflake` · `duckdb` · `airflow` · `rag` · `data-engineering`
· `clinical-trials` · `llm` · `terraform` · `python`
