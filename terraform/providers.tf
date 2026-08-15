terraform {
  # exact provider pins per the determinism policy; the committed
  # .terraform.lock.hcl additionally pins checksums
  required_version = "~> 1.15.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "6.60.0"
    }
    snowflake = {
      source  = "snowflakedb/snowflake"
      version = "2.19.0"
    }
  }

  # backend: local (default, no block needed). Single developer, and
  # *.tfstate is gitignored — state can hold sensitive values. Scaling
  # path (S3 backend + locking) is a DECISIONS.md note, not code.
}

provider "aws" {
  region = var.aws_region
  # credentials come only from the AWS_PROFILE env var (.env) — never here
}

provider "snowflake" {
  # connection comes only from SNOWFLAKE_* env vars (see README.md) —
  # never here. Run with a role that can CREATE INTEGRATION (ACCOUNTADMIN).
  # the only used resource still marked preview in provider 2.19.0
  # (storage_integration_aws and stage_external_s3 are stable)
  preview_features_enabled = [
    "snowflake_file_format_parquet_resource",
  ]
}
