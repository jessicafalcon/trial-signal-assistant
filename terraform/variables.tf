variable "aws_region" {
  type        = string
  description = "AWS region for the landing bucket and IAM role."
  default     = "eu-west-3"
}

variable "s3_bucket_name" {
  type        = string
  description = <<-EOT
    Raw landing bucket. Bucket names are globally unique — override
    (TF_VAR_s3_bucket_name) if the default is taken at apply time.
    The Makefile duplicates this default as S3_BUCKET — an override
    here must be mirrored there (single-sourcing: phase 7 checklist).
  EOT
  default     = "trial-signal-raw-landing"
}

variable "snowflake_iam_role_name" {
  type        = string
  description = "Name of the IAM role Snowflake assumes to read the bucket."
  default     = "trial-signal-snowflake-access"
}

variable "snowflake_admin_user" {
  type        = string
  description = <<-EOT
    Existing Snowflake user granted the TRANSFORMER role (the trial's
    admin user). No default on purpose: pass via
    TF_VAR_snowflake_admin_user, never a committed file.
  EOT
}
