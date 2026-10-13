# Compute child module input variables (task 15.1).

variable "name_prefix" {
  description = "Prefix applied to resource names (e.g. strands-rag-dev)."
  type        = string
}

# ---------------------------------------------------------------------------
# Networking wiring (Req 11.4) — from the networking module outputs.
# ---------------------------------------------------------------------------
variable "private_subnet_ids" {
  description = "Private subnet IDs (from networking) for the Lambda VPC configuration."
  type        = list(string)
}

variable "lambda_security_group_id" {
  description = "Security group ID (from networking) attached to the Lambda functions."
  type        = string
}

# ---------------------------------------------------------------------------
# Data-tier wiring (from the data module outputs).
# ---------------------------------------------------------------------------
variable "session_table_name" {
  description = "DynamoDB session table name (environment variable for the chat handler)."
  type        = string
}

variable "session_table_arn" {
  description = "DynamoDB session table ARN (scoped IAM resource)."
  type        = string
}

variable "analytics_table_name" {
  description = "DynamoDB analytics table name (environment variable)."
  type        = string
}

variable "analytics_table_arn" {
  description = "DynamoDB analytics table ARN (scoped IAM resource)."
  type        = string
}

variable "opensearch_collection_arn" {
  description = "OpenSearch Serverless collection ARN (scoped aoss:APIAccessAll resource)."
  type        = string
}

variable "opensearch_collection_endpoint" {
  description = "OpenSearch Serverless collection endpoint (environment variable)."
  type        = string
}

variable "opensearch_kb_index" {
  description = "OpenSearch knowledge-base index name."
  type        = string
  default     = "rag-kb"
}

variable "opensearch_cache_index" {
  description = "OpenSearch Layer-4 semantic cache index name."
  type        = string
  default     = "rag-cache"
}

variable "redis_primary_endpoint" {
  description = "Redis primary (write) endpoint address (environment variable)."
  type        = string
}

variable "redis_port" {
  description = "Redis port (environment variable)."
  type        = number
  default     = 6379
}

# ---------------------------------------------------------------------------
# Bedrock model configuration (Req 5.x) — mirrors the root variables.
# ---------------------------------------------------------------------------
variable "bedrock_inference_model_id" {
  description = "Bedrock inference (generation) model ID."
  type        = string
  default     = "amazon.nova-lite-v1:0"
}

variable "bedrock_embedding_model_id" {
  description = "Bedrock embedding model ID (produces 1536-dim vectors)."
  type        = string
  default     = "amazon.titan-embed-text-v1"
}

variable "bedrock_model_override" {
  description = "Optional Bedrock model ID override. Empty string means no override."
  type        = string
  default     = ""
}

# ---------------------------------------------------------------------------
# Lambda sizing (Req 11.x). Memory 2048; chat up to 120s; indexing up to 300s.
# ---------------------------------------------------------------------------
variable "lambda_memory_size" {
  description = "Memory (MB) for both Lambda functions."
  type        = number
  default     = 2048

  validation {
    condition     = var.lambda_memory_size >= 128 && var.lambda_memory_size <= 10240
    error_message = "lambda_memory_size must be between 128 and 10240 MB."
  }
}

variable "chat_timeout" {
  description = "Timeout (seconds) for the chat handler Lambda (up to 120s)."
  type        = number
  default     = 120

  validation {
    condition     = var.chat_timeout >= 1 && var.chat_timeout <= 120
    error_message = "chat_timeout must be between 1 and 120 seconds."
  }
}

variable "indexing_timeout" {
  description = "Timeout (seconds) for the indexing handler Lambda (up to 300s)."
  type        = number
  default     = 300

  validation {
    condition     = var.indexing_timeout >= 1 && var.indexing_timeout <= 900
    error_message = "indexing_timeout must be between 1 and 900 seconds."
  }
}

# ---------------------------------------------------------------------------
# Lambda packaging (Req packaging note). CI overrides these with the real zip.
# ---------------------------------------------------------------------------
variable "lambda_package_path" {
  description = "Path to the Lambda deployment zip built by CI. When null, a placeholder archive is built so the module validates/plans without a real artifact."
  type        = string
  default     = null
}

variable "lambda_source_code_hash" {
  description = "Base64 SHA-256 of the Lambda deployment zip (from CI). When null, the placeholder archive hash is used."
  type        = string
  default     = null
}

# ---------------------------------------------------------------------------
# S3 documents bucket wiring (Req 9.1).
#
# The documents bucket is created in the frontend module (task 17). These
# inputs default to null so this module validates standalone; the root wires
# the real bucket id/arn in once the frontend module exists, which enables the
# aws_lambda_permission + aws_s3_bucket_notification resources (count = 1).
# ---------------------------------------------------------------------------
variable "documents_bucket_id" {
  description = "S3 documents bucket id/name (from the frontend module). null disables the S3 ObjectCreated trigger for standalone validation."
  type        = string
  default     = null
}

variable "documents_bucket_arn" {
  description = "S3 documents bucket ARN (from the frontend module). null disables the S3 trigger and widens the S3 read IAM resource to a name-prefixed pattern."
  type        = string
  default     = null
}

variable "documents_prefix" {
  description = "S3 key prefix that triggers indexing (Req 9.1 — the documents/ prefix)."
  type        = string
  default     = "documents/"
}

variable "tags" {
  description = "Tags applied to all compute-tier resources."
  type        = map(string)
  default     = {}
}
