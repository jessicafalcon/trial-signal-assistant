# Public flip checklist (human-only, in this order)

From SPEC-07's human gates plus the phase-7 ruled additions. Execute
top to bottom; nothing here is automatable by design. Steps 1–2 of
the original list are done: the final whole-tree audit was ruled
(2026-08-16 — its one gate resolved by the history scrub below) and
the phase-7 PR is merged.

1. Apply the S3 lifecycle change if not yet applied:
   `terraform -chdir=terraform plan` (expect: 1 to add,
   aws_s3_bucket_lifecycle_configuration.raw_landing), then apply.
2. **Force-push the scrubbed history** (rewritten locally 2026-08-16;
   DECISIONS.md history-rewrite entry has the hash map):

       git remote add origin git@github.com:jessicafalcon/trial-signal-assistant.git
       git push --force-with-lease=refs/heads/main:9ceba921f487bce22a99d81ce2d446a25a54b128 origin main
       git push origin --delete demo-capture phase-2-dbt-staging \
         phase-3-change-detection phase-4-cloud-target phase-5-rag-layer \
         phase-6-orchestration phase-7-packaging

   The lease value is the old main tip: the push fails if origin
   moved. Obsolete remote branches are deleted, not rewritten.
3. **Verify from a fresh clone** (values for the three placeholder
   strings are in the final audit report — do not write them into
   any repo file):

       git clone git@github.com:jessicafalcon/trial-signal-assistant.git /tmp/verify-clone
       cd /tmp/verify-clone
       for s in '<SURNAME>' '<EMAIL>' '<PHONE>'; do
         git grep -F -l -e "$s" $(git rev-list --all) | wc -l   # expect 0, three times
       done
       git cat-file -e a33d640c0b18d9380d43b35b959b0e201d68d34b || echo "old blob absent (good)"

4. Purge of GitHub's cached copies — **WAIVED** by owner ruling
   2026-08-16 (DECISIONS.md "Flip step 4 waived"). PR history #1–#8
   is kept; the pre-scrub commits stay reachable on GitHub via
   refs/pull/* and direct SHA URLs (they do not reach default
   clones). Accepted because the only scrubbed content is
   already-public registry contact data — no secrets. Proceed
   directly to step 5.
5. Set the GitHub repo description and topics (drafts below).
6. Settings → Danger Zone → change visibility to Public.
7. IMMEDIATELY enable branch protection on main — require the lint,
   test, dbt, dag-verify, terraform, and secrets checks. This is not
   cosmetic: the CI self-governance guards (base-branch gitleaks
   config + base-branch floor script) run on pull requests only, so a
   direct push to main bypasses them. Branch protection is what
   closes that hole after the flip.
8. Add the repo link to CV/profile.

## Repo description draft

> Clinical trial data pipeline + RAG assistant: dbt on DuckDB/Snowflake,
> SCD2 status-change tracking, Airflow orchestration, and cited Claude
> answers over ClinicalTrials.gov data. Deterministic middle, AI at the
> edges.

## Topics draft

`dbt` · `snowflake` · `duckdb` · `airflow` · `rag` · `data-engineering`
· `clinical-trials` · `llm` · `terraform` · `python`
