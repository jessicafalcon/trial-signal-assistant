output "s3_bucket_name" {
  value       = aws_s3_bucket.raw_landing.bucket
  description = "Raw landing bucket (make s3-sync destination)."
}

output "s3_parsed_prefix" {
  value       = local.parsed_prefix
  description = "Bucket prefix holding parsed parquet partitions."
}

output "snowflake_stage" {
  value       = snowflake_stage_external_s3.parsed_trials.fully_qualified_name
  description = "External stage COPY INTO reads from."
}

output "snowflake_warehouse" {
  value       = snowflake_warehouse.transform.name
  description = "Warehouse for load + dbt (SNOWFLAKE_WAREHOUSE)."
}

output "transformer_role" {
  value       = snowflake_account_role.transformer.name
  description = "Role for load + dbt (SNOWFLAKE_ROLE)."
}

output "storage_aws_iam_user_arn" {
  value       = snowflake_storage_integration_aws.s3_raw.describe_output[0].iam_user_arn
  description = "Snowflake-side IAM user trusted by the S3 access role."
}

output "storage_aws_external_id" {
  value       = snowflake_storage_integration_aws.s3_raw.describe_output[0].external_id
  description = "External ID in the role trust policy — treated as a secret."
  sensitive   = true
}
