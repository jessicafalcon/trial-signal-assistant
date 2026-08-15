# Terraform — S3 landing + Snowflake objects

Provisions the phase-4 cloud path: the S3 raw landing bucket, the IAM
role Snowflake assumes to read it, and the Snowflake side (database,
schemas, warehouse, TRANSFORMER role, storage integration, parquet file
format, external stage).

State is local (`terraform.tfstate`, gitignored — it can contain
sensitive values). `.terraform.lock.hcl` IS committed: it pins provider
checksums, per the determinism policy.

## Prerequisites

- terraform ~> 1.15, aws CLI (see repo README setup).
- AWS: the `AWS_PROFILE` from `.env`. NOTE: the apply creates an IAM
  role + inline policy, so the profile's IAM user needs `iam:CreateRole`,
  `iam:PutRolePolicy`, `iam:GetRole`, `iam:TagRole` (and the delete/list
  equivalents for destroy) on top of S3 — an "S3-only" user cannot apply.
- Snowflake: the provider reads only these env vars (no values in any
  file):
  - `SNOWFLAKE_ORGANIZATION_NAME` and `SNOWFLAKE_ACCOUNT_NAME` — the two
    halves of dbt's `SNOWFLAKE_ACCOUNT` (`<org>-<account>`).
  - `SNOWFLAKE_ACCOUNT` itself must be UNSET in the terraform shell:
    the provider reads it as the removed legacy `account` field and
    errors ("PROVIDER_CONFIGURATION_ACCOUNT_FALLBACK experiment").
  - `SNOWFLAKE_WAREHOUSE` must be UNSET too: the provider opens its
    session with it, and the warehouse doesn't exist until this apply
    creates it (error 390201). DDL needs no warehouse.
  - `SNOWFLAKE_USER`, `SNOWFLAKE_PASSWORD`.
  - `SNOWFLAKE_ROLE=ACCOUNTADMIN` — `CREATE STORAGE INTEGRATION`
    requires it on a fresh trial.
- `TF_VAR_snowflake_admin_user` — the Snowflake user that gets the
  TRANSFORMER role, exact case per SHOW USERS' name column (the
  provider quotes identifiers). Fine to keep in `.env` — it is a
  username, not a secret.

## Apply sequence

```sh
unset SNOWFLAKE_ACCOUNT SNOWFLAKE_WAREHOUSE   # see prerequisites above
cd terraform
terraform init
terraform plan    # review: no secrets in the diff
terraform apply
terraform plan    # convergence proof: must print "No changes."
```

The storage-integration ⇄ IAM-role trust handshake is the classically
two-phase part: Snowflake mints an IAM user ARN + external ID only when
the integration is created, and the IAM role's trust policy must contain
both. Here the provider exposes them as computed attributes
(`describe_output`), so Terraform creates the integration first and the
IAM role second within ONE apply; the final `terraform plan` is the
proof it converged. If Snowflake ever re-mints the identities (e.g. the
integration is recreated), the same single `apply` re-syncs the trust
policy.

If the first `COPY INTO` after an apply fails with an access error,
wait ~30s and retry — IAM trust-policy changes propagate with a small
delay.

## Never commit

`terraform.tfstate*`, `*.tfvars`, `.terraform/` — all gitignored;
credentials exist only as env vars.
