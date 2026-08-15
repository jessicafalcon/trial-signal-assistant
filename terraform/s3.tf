data "aws_caller_identity" "current" {}

locals {
  # constructed instead of aws_iam_role.snowflake_access.arn: the storage
  # integration needs this ARN, and the role's trust policy needs the
  # integration's outputs — referencing the role would be a cycle.
  snowflake_iam_role_arn = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/${var.snowflake_iam_role_name}"

  # parsed parquet lands under this prefix (make s3-sync); raw JSON gets
  # its own prefix in a later phase, so the bucket root stays partitioned
  parsed_prefix = "parsed"
}

resource "aws_s3_bucket" "raw_landing" {
  bucket = var.s3_bucket_name
}

resource "aws_s3_bucket_public_access_block" "raw_landing" {
  bucket                  = aws_s3_bucket.raw_landing.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "raw_landing" {
  bucket = aws_s3_bucket.raw_landing.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "raw_landing" {
  bucket = aws_s3_bucket.raw_landing.id

  versioning_configuration {
    status = "Enabled"
  }
}

# Trust policy: only Snowflake's IAM user, and only with the external ID
# minted for this integration, may assume the role. Both values are
# computed attributes of the storage integration, so Terraform creates
# the integration first and this role second — no second apply needed.
data "aws_iam_policy_document" "snowflake_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "AWS"
      identifiers = [snowflake_storage_integration_aws.s3_raw.describe_output[0].iam_user_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "sts:ExternalId"
      values   = [snowflake_storage_integration_aws.s3_raw.describe_output[0].external_id]
    }
  }
}

# read-only, parsed/ prefix only — least privilege for COPY INTO
data "aws_iam_policy_document" "snowflake_s3_read" {
  statement {
    sid = "ReadParsedObjects"
    actions = [
      "s3:GetObject",
      "s3:GetObjectVersion",
    ]
    resources = ["${aws_s3_bucket.raw_landing.arn}/${local.parsed_prefix}/*"]
  }

  statement {
    sid       = "ListParsedPrefix"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.raw_landing.arn]

    # s3:prefix only exists on ListBucket requests — keep
    # GetBucketLocation in its own unconditioned statement
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["${local.parsed_prefix}/*"]
    }
  }

  statement {
    sid       = "GetBucketLocation"
    actions   = ["s3:GetBucketLocation"]
    resources = [aws_s3_bucket.raw_landing.arn]
  }
}

# the public access block stops public GRANTS; this policy additionally
# refuses any request arriving without TLS
data "aws_iam_policy_document" "raw_landing_tls_only" {
  statement {
    sid     = "DenyInsecureTransport"
    effect  = "Deny"
    actions = ["s3:*"]
    resources = [
      aws_s3_bucket.raw_landing.arn,
      "${aws_s3_bucket.raw_landing.arn}/*",
    ]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "raw_landing" {
  bucket = aws_s3_bucket.raw_landing.id
  policy = data.aws_iam_policy_document.raw_landing_tls_only.json

  # the public access block must exist first, or PutBucketPolicy can
  # race with block_public_policy
  depends_on = [aws_s3_bucket_public_access_block.raw_landing]
}

resource "aws_iam_role" "snowflake_access" {
  name               = var.snowflake_iam_role_name
  assume_role_policy = data.aws_iam_policy_document.snowflake_trust.json
}

resource "aws_iam_role_policy" "snowflake_s3_read" {
  name   = "s3-read-parsed"
  role   = aws_iam_role.snowflake_access.id
  policy = data.aws_iam_policy_document.snowflake_s3_read.json
}
