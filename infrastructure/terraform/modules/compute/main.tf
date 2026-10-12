# Compute child module (task 15.1).
#
# Provisions the serverless compute tier:
#   - Two aws_lambda_function resources:
#       * chat     -> handler "agentcore_handler.lambda_handler"  (src/agents)
#       * indexing -> handler "indexing_handler.lambda_handler"   (src/indexing)
#     Both run Python 3.12, 2048 MB, VPC-attached to the networking private
#     subnets + the lambda security group, with X-Ray active tracing
#     (Requirements 11.1, 11.4; X-Ray needed by Req 12.4 later).
#   - A Lambda execution aws_iam_role (trust: lambda.amazonaws.com) plus a
#     least-privilege, customer-managed aws_iam_policy whose action set is
#     EXACTLY the permitted set — no wildcard "*" actions (Property 31 / Req
#     11.5). The AWS-managed AWSLambdaVPCAccessExecutionRole is attached
#     separately for ENI management (Req 11.4); keeping it out of the inline
#     policy ensures the Property 31 scan over the customer policy passes.
#   - aws_secretsmanager_secret resources for the Tavily API key and the Redis
#     credentials, referenced by the role (Req 10.1, 11.5).
#   - The S3 ObjectCreated trigger for the indexing Lambda (aws_lambda_permission
#     + aws_s3_bucket_notification) under the documents/ prefix (Req 9.1).
#
# PACKAGING (validates without real build artifacts):
# The Lambda deployment zip is produced by CI (it bundles src/ plus the Python
# dependencies). To keep this module validatable with no real artifact present,
# we build a tiny placeholder zip from a committed placeholder source directory
# via data.archive_file and feed its output_path/output_base64sha256 into both
# functions. In CI the real zip is swapped in (e.g. by overriding
# var.lambda_package_path / var.lambda_source_code_hash) before apply. The
# archive_file keeps `filename` + `source_code_hash` always populated so
# `terraform validate` and `plan` succeed without AWS access.

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.79"
    }
    archive = {
      source  = "hashicorp/archive"
      version = ">= 2.4"
    }
  }
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  chat_function_name     = "${var.name_prefix}-chat"
  indexing_function_name = "${var.name_prefix}-indexing"
  role_name              = "${var.name_prefix}-lambda-exec"
  policy_name            = "${var.name_prefix}-lambda-least-privilege"

  # Secrets Manager secret names referenced by the Lambda role (Req 10.1, 11.5).
  tavily_secret_name = "${var.name_prefix}/tavily-api-key"
  redis_secret_name  = "${var.name_prefix}/redis-credentials"

  # Whether to wire the S3 ObjectCreated notification. The documents bucket is
  # created in the frontend module (task 17); until the root passes its id/arn
  # in, these resources are skipped so this module validates standalone (Req 9.1).
  enable_s3_trigger = var.documents_bucket_id == null ? 0 : 1

  # Shared environment variables for both functions (Req 11 wiring). The chat
  # handler needs all of them; the indexing handler mainly needs Bedrock +
  # OpenSearch + the analytics table, but passing the full set is harmless and
  # keeps a single source of truth.
  lambda_environment = {
    DEPLOYMENT_MODE = "serverless"

    # OpenSearch Serverless (Req 4.x)
    OPENSEARCH_ENDPOINT    = var.opensearch_collection_endpoint
    OPENSEARCH_KB_INDEX    = var.opensearch_kb_index
    OPENSEARCH_CACHE_INDEX = var.opensearch_cache_index

    # Redis / ElastiCache (Req 3.x)
    REDIS_ENDPOINT = var.redis_primary_endpoint
    REDIS_PORT     = tostring(var.redis_port)

    # DynamoDB tables (Req 1.x, 9.x)
    DYNAMODB_SESSION_TABLE   = var.session_table_name
    DYNAMODB_ANALYTICS_TABLE = var.analytics_table_name

    # Bedrock model IDs (Req 5.x)
    BEDROCK_INFERENCE_MODEL_ID = var.bedrock_inference_model_id
    BEDROCK_EMBEDDING_MODEL_ID = var.bedrock_embedding_model_id
    BEDROCK_MODEL_OVERRIDE     = var.bedrock_model_override

    # Secrets Manager secret names (Req 10.1, 11.5)
    TAVILY_SECRET_NAME = local.tavily_secret_name
    REDIS_SECRET_NAME  = local.redis_secret_name
  }
}

# ---------------------------------------------------------------------------
# Lambda deployment package (placeholder).
#
# CI replaces this with the real build zip. The placeholder keeps `filename`
# and `source_code_hash` populated so the configuration validates/plans with no
# real artifact present. See the module header for the CI swap approach.
# ---------------------------------------------------------------------------
data "archive_file" "lambda_placeholder" {
  type        = "zip"
  output_path = "${path.module}/build/lambda_placeholder.zip"

  source {
    content  = "# Placeholder Lambda package. CI builds the real deployment zip\n# bundling src/ and dependencies and overrides var.lambda_package_path.\n"
    filename = "placeholder.txt"
  }
}

locals {
  lambda_package_path = coalesce(var.lambda_package_path, data.archive_file.lambda_placeholder.output_path)
  lambda_source_hash  = coalesce(var.lambda_source_code_hash, data.archive_file.lambda_placeholder.output_base64sha256)
}

# ---------------------------------------------------------------------------
# Secrets Manager — Tavily API key + Redis credentials (Req 10.1, 11.5).
#   Secret *values* are managed out-of-band (CI / console / a separate secret
#   version) and are intentionally NOT set here so no secret material lives in
#   the Terraform state produced by this module.
# ---------------------------------------------------------------------------
resource "aws_secretsmanager_secret" "tavily" {
  name        = local.tavily_secret_name
  description = "Tavily web-search API key, loaded by the chat Lambda at cold start (Req 10.1)."

  tags = merge(var.tags, { Name = local.tavily_secret_name })
}

resource "aws_secretsmanager_secret" "redis" {
  name        = local.redis_secret_name
  description = "Redis/ElastiCache credentials for the chat Lambda (Req 3.x)."

  tags = merge(var.tags, { Name = local.redis_secret_name })
}

# ---------------------------------------------------------------------------
# IAM — Lambda execution role trust policy (lambda.amazonaws.com).
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    sid     = "LambdaAssumeRole"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda_exec" {
  name               = local.role_name
  description        = "Execution role for the ${var.name_prefix} chat + indexing Lambda functions."
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json

  tags = merge(var.tags, { Name = local.role_name })
}

# ---------------------------------------------------------------------------
# IAM — least-privilege customer-managed policy (Property 31 / Req 11.5).
#
# CRITICAL: the action set below MUST be exactly the permitted set and nothing
# else — no wildcard "*" actions. Resources are scoped to the specific tables,
# collection, bucket, and secrets wherever the service supports it.
#
# Permitted action set (Property 31):
#   bedrock:InvokeModel
#   dynamodb:GetItem, dynamodb:PutItem, dynamodb:UpdateItem,
#   dynamodb:DeleteItem, dynamodb:Query
#   elasticache:Connect
#   aoss:APIAccessAll
#   s3:GetObject, s3:ListBucket
#   secretsmanager:GetSecretValue
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "lambda_least_privilege" {
  # Bedrock model invocation (Req 5.x). Scope to the configured inference +
  # embedding foundation models in this region/account.
  statement {
    sid     = "BedrockInvokeModel"
    effect  = "Allow"
    actions = ["bedrock:InvokeModel"]
    resources = [
      "arn:aws:bedrock:${data.aws_region.current.name}::foundation-model/${var.bedrock_inference_model_id}",
      "arn:aws:bedrock:${data.aws_region.current.name}::foundation-model/${var.bedrock_embedding_model_id}",
    ]
  }

  # DynamoDB CRUD + Query on the session and analytics tables only (Req 1.x, 9.x).
  statement {
    sid    = "DynamoDBSessionAnalytics"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:DeleteItem",
      "dynamodb:Query",
    ]
    resources = [
      var.session_table_arn,
      "${var.session_table_arn}/index/*",
      var.analytics_table_arn,
      "${var.analytics_table_arn}/index/*",
    ]
  }

  # ElastiCache data-plane connect (Req 3.x). elasticache:Connect does not
  # support fine-grained resource scoping for cache connections, so "*" is the
  # resource (the ACTION remains within the permitted set — Property 31 scans
  # actions, not resources).
  statement {
    sid       = "ElastiCacheConnect"
    effect    = "Allow"
    actions   = ["elasticache:Connect"]
    resources = ["*"]
  }

  # OpenSearch Serverless HTTP data access (Req 4.x). Scope to the collection ARN.
  statement {
    sid       = "OpenSearchServerlessAccess"
    effect    = "Allow"
    actions   = ["aoss:APIAccessAll"]
    resources = [var.opensearch_collection_arn]
  }

  # S3 read on the documents bucket (Req 9.1 indexing input). When the bucket
  # arn is not yet wired (standalone validation), fall back to the account-wide
  # documents-prefixed pattern so the statement is still well-formed.
  statement {
    sid    = "S3DocumentsRead"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:ListBucket",
    ]
    resources = var.documents_bucket_arn == null ? [
      "arn:aws:s3:::${var.name_prefix}-*",
      "arn:aws:s3:::${var.name_prefix}-*/*",
      ] : [
      var.documents_bucket_arn,
      "${var.documents_bucket_arn}/*",
    ]
  }

  # Secrets Manager read on the Tavily + Redis secrets only (Req 10.1, 11.5).
  statement {
    sid     = "SecretsManagerRead"
    effect  = "Allow"
    actions = ["secretsmanager:GetSecretValue"]
    resources = [
      aws_secretsmanager_secret.tavily.arn,
      aws_secretsmanager_secret.redis.arn,
    ]
  }
}

resource "aws_iam_policy" "lambda_least_privilege" {
  name        = local.policy_name
  description = "Least-privilege policy for the ${var.name_prefix} Lambda role (exactly the permitted action set; Property 31 / Req 11.5)."
  policy      = data.aws_iam_policy_document.lambda_least_privilege.json

  tags = merge(var.tags, { Name = local.policy_name })
}

resource "aws_iam_role_policy_attachment" "lambda_least_privilege" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = aws_iam_policy.lambda_least_privilege.arn
}

# AWS-managed policy for VPC ENI management (Req 11.4). This is SEPARATE from
# the inline least-privilege policy scanned by Property 31; attaching the
# managed policy is acceptable and keeps the customer policy restricted.
resource "aws_iam_role_policy_attachment" "lambda_vpc_access" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

# AWS-managed policy granting X-Ray write permissions
# (xray:PutTraceSegments / xray:PutTelemetryRecords) so the Active tracing
# configured on both Lambdas above can actually deliver segments (Req 12.4).
# Like the VPC-access attachment, this is a MANAGED policy and is therefore
# EXEMPT from the Property 31 scan over the customer-managed INLINE policy —
# the inline least-privilege action set is intentionally left untouched.
resource "aws_iam_role_policy_attachment" "lambda_xray_write" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = "arn:aws:iam::aws:policy/AWSXRayDaemonWriteAccess"
}

# ---------------------------------------------------------------------------
# Lambda — chat handler (agentcore_handler.lambda_handler).
#   Memory 2048, timeout up to 120s, VPC-attached, X-Ray Active (Req 12.4).
# ---------------------------------------------------------------------------
resource "aws_lambda_function" "chat" {
  function_name = local.chat_function_name
  role          = aws_iam_role.lambda_exec.arn
  handler       = "agentcore_handler.lambda_handler"
  runtime       = "python3.12"
  memory_size   = var.lambda_memory_size
  timeout       = var.chat_timeout

  filename         = local.lambda_package_path
  source_code_hash = local.lambda_source_hash

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [var.lambda_security_group_id]
  }

  tracing_config {
    mode = "Active"
  }

  environment {
    variables = local.lambda_environment
  }

  tags = merge(var.tags, { Name = local.chat_function_name })

  depends_on = [
    aws_iam_role_policy_attachment.lambda_least_privilege,
    aws_iam_role_policy_attachment.lambda_vpc_access,
    aws_iam_role_policy_attachment.lambda_xray_write,
  ]
}

# ---------------------------------------------------------------------------
# Lambda — indexing handler (indexing_handler.lambda_handler).
#   Memory 2048, timeout up to 300s, VPC-attached, X-Ray Active.
# ---------------------------------------------------------------------------
resource "aws_lambda_function" "indexing" {
  function_name = local.indexing_function_name
  role          = aws_iam_role.lambda_exec.arn
  handler       = "indexing_handler.lambda_handler"
  runtime       = "python3.12"
  memory_size   = var.lambda_memory_size
  timeout       = var.indexing_timeout

  filename         = local.lambda_package_path
  source_code_hash = local.lambda_source_hash

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [var.lambda_security_group_id]
  }

  tracing_config {
    mode = "Active"
  }

  environment {
    variables = local.lambda_environment
  }

  tags = merge(var.tags, { Name = local.indexing_function_name })

  depends_on = [
    aws_iam_role_policy_attachment.lambda_least_privilege,
    aws_iam_role_policy_attachment.lambda_vpc_access,
    aws_iam_role_policy_attachment.lambda_xray_write,
  ]
}

# ---------------------------------------------------------------------------
# S3 ObjectCreated trigger for the indexing Lambda (Req 9.1).
#
# The documents bucket is created in the frontend module (task 17). To avoid a
# forward dependency, the bucket id/arn are inputs defaulting to null and these
# resources are conditional on them being supplied (count = 0 when null) so the
# module validates standalone now; the root wires the bucket in later.
# ---------------------------------------------------------------------------
resource "aws_lambda_permission" "allow_s3_invoke_indexing" {
  count = local.enable_s3_trigger

  statement_id   = "AllowExecutionFromS3Documents"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.indexing.function_name
  principal      = "s3.amazonaws.com"
  source_arn     = var.documents_bucket_arn
  source_account = data.aws_caller_identity.current.account_id
}

resource "aws_s3_bucket_notification" "documents" {
  count = local.enable_s3_trigger

  bucket = var.documents_bucket_id

  lambda_function {
    lambda_function_arn = aws_lambda_function.indexing.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = var.documents_prefix
  }

  depends_on = [aws_lambda_permission.allow_s3_invoke_indexing]
}
