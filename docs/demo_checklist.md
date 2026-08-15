# Demo capture checklist (human-executed, after phase-6 merge, on main)

Run everything live first (`cd airflow && astro dev start`, trigger a
run, wait for all-green), then capture in this order. Store captures
under a location of your choosing (not `data/` — it is gitignored and
purpose-bound).

## Captures

- [ ] **Airflow graph view, one all-green run** (the money shot):
      UI → trial_safety_pipeline → Graph, all 11 tasks green.
- [ ] **Snowsight — schemas + row count**: TRIAL_SIGNAL database
      showing RAW / ANALYTICS schemas, and
      `select count(*) from trial_signal.raw.trials;` with its result.
- [ ] **Warehouse config + cost**: TRIAL_SIGNAL_WH settings page
      showing `auto_suspend = 60`, and Admin → Cost Management after a
      full run — note the credit burn number for the README.
- [ ] **Terminal — `make ask` full JSON**:
      `make ask Q="why was the tezepelumab trial stopped?"`
      (needs `ANTHROPIC_API_KEY`; capture the full JSON including
      `cited_nct_ids`).
- [ ] **Terminal — `make eval` summary table** (the 10-question golden
      eval with both scores).
- [ ] **Terraform convergence**: tail of `terraform -chdir=terraform
      plan` ending in "No changes." (unset `SNOWFLAKE_ACCOUNT` /
      `SNOWFLAKE_WAREHOUSE` in that shell first — see
      terraform/README.md).
- [ ] *(optional)* **GIF**: trigger → tasks lighting up green in the
      graph view.

## Notes

- The same-day re-trigger is safe (end-to-end no-op) if a second
  all-green run is wanted for the GIF.
- Credentials: `.env` / `~/.aws` only. Nothing captured may show env
  values — crop terminal frames to command + output.
