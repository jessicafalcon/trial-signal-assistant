resource "snowflake_database" "trial_signal" {
  name    = "TRIAL_SIGNAL"
  comment = "Clinical trial signal assistant — demo warehouse target."
}

resource "snowflake_schema" "raw" {
  database = snowflake_database.trial_signal.name
  name     = "RAW"
  comment  = "Landing schema: external stage + COPY INTO target (TRIALS)."
}

resource "snowflake_schema" "analytics" {
  database = snowflake_database.trial_signal.name
  name     = "ANALYTICS"
  comment  = "dbt build target schema (snowflake profile target)."
}

resource "snowflake_warehouse" "transform" {
  name = "TRIAL_SIGNAL_WH"
  # auto_resume is a string enum in this provider version, not a bool
  warehouse_size      = "XSMALL"
  auto_suspend        = 60
  auto_resume         = "true"
  initially_suspended = true
  comment             = "XS demo warehouse; 60s auto-suspend keeps trial credit burn minimal."
}

resource "snowflake_account_role" "transformer" {
  name    = "TRANSFORMER"
  comment = "Least-privilege role for COPY INTO and dbt builds."
}

resource "snowflake_grant_account_role" "transformer_to_admin" {
  role_name = snowflake_account_role.transformer.name
  user_name = var.snowflake_admin_user
}

resource "snowflake_grant_privileges_to_account_role" "db_usage" {
  account_role_name = snowflake_account_role.transformer.name
  privileges        = ["USAGE"]

  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.trial_signal.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "warehouse_usage" {
  account_role_name = snowflake_account_role.transformer.name
  privileges        = ["USAGE"]

  on_account_object {
    object_type = "WAREHOUSE"
    object_name = snowflake_warehouse.transform.name
  }
}

# CREATE TABLE in RAW covers the load path (the loader runs as
# TRANSFORMER and owns what it creates); the explicit SELECT grants
# below keep dbt's read access even if RAW.TRIALS is ever recreated by
# another role (2026-08-15 review ruling F14).
resource "snowflake_grant_privileges_to_account_role" "raw_schema" {
  account_role_name = snowflake_account_role.transformer.name
  privileges        = ["USAGE", "CREATE TABLE"]

  on_schema {
    schema_name = snowflake_schema.raw.fully_qualified_name
  }
}

resource "snowflake_grant_privileges_to_account_role" "raw_tables_select_all" {
  account_role_name = snowflake_account_role.transformer.name
  privileges        = ["SELECT"]

  on_schema_object {
    all {
      object_type_plural = "TABLES"
      in_schema          = snowflake_schema.raw.fully_qualified_name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "raw_tables_select_future" {
  account_role_name = snowflake_account_role.transformer.name
  privileges        = ["SELECT"]

  on_schema_object {
    future {
      object_type_plural = "TABLES"
      in_schema          = snowflake_schema.raw.fully_qualified_name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "analytics_schema" {
  account_role_name = snowflake_account_role.transformer.name
  privileges        = ["USAGE", "CREATE TABLE", "CREATE VIEW"]

  on_schema {
    schema_name = snowflake_schema.analytics.fully_qualified_name
  }
}

# Storage integration: Snowflake-side half of the S3 trust handshake.
# The IAM user ARN and external ID Snowflake mints for it surface in
# describe_output and feed the IAM role trust policy in s3.tf.
resource "snowflake_storage_integration_aws" "s3_raw" {
  name                      = "TRIAL_SIGNAL_S3"
  storage_provider          = "S3"
  enabled                   = true
  storage_aws_role_arn      = local.snowflake_iam_role_arn
  storage_allowed_locations = ["s3://${aws_s3_bucket.raw_landing.bucket}/${local.parsed_prefix}/"]
  comment                   = "Read-only bridge to the S3 raw landing bucket (parsed/ prefix)."
}

resource "snowflake_file_format_parquet" "parquet" {
  name     = "PARQUET_FORMAT"
  database = snowflake_database.trial_signal.name
  schema   = snowflake_schema.raw.name
  comment  = "COPY INTO format for the parsed trial parquet."
}

resource "snowflake_stage_external_s3" "parsed_trials" {
  name                = "PARSED_TRIALS"
  database            = snowflake_database.trial_signal.name
  schema              = snowflake_schema.raw.name
  url                 = "s3://${aws_s3_bucket.raw_landing.bucket}/${local.parsed_prefix}/"
  storage_integration = snowflake_storage_integration_aws.s3_raw.name
  comment             = "External stage over the parsed parquet partitions."

  file_format {
    format_name = snowflake_file_format_parquet.parquet.fully_qualified_name
  }
}

resource "snowflake_grant_privileges_to_account_role" "stage_usage" {
  account_role_name = snowflake_account_role.transformer.name
  privileges        = ["USAGE"]

  on_schema_object {
    object_type = "STAGE"
    object_name = snowflake_stage_external_s3.parsed_trials.fully_qualified_name
  }
}

resource "snowflake_grant_privileges_to_account_role" "file_format_usage" {
  account_role_name = snowflake_account_role.transformer.name
  privileges        = ["USAGE"]

  on_schema_object {
    object_type = "FILE FORMAT"
    object_name = snowflake_file_format_parquet.parquet.fully_qualified_name
  }
}
