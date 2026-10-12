# Root module input variables.
#
# Environment-specific values (stage, Bedrock model, Redis node type, OpenSearch
# capacity, VPC CIDR) are supplied via per-environment tfvars files so the same
# configuration deploys to dev, staging, and prod with no code changes
# (Requirement 11.2).

variable "stage" {
  description = "Deployment stage/environment name (e.g. dev, staging, prod). Used as a resource name prefix."
  type        = string

  validation {
    condition     = contains(["dev", "staging", "prod"], var.stage)
    error_message = "stage must be one of: dev, staging, prod."
  }
}

variable "aws_region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "us-east-1"
}

# ---------------------------------------------------------------------------
# Bedrock model configuration (Requirement 5.1, 5.2, 5.4)
# ---------------------------------------------------------------------------

variable "bedrock_inference_model_id" {
  description = "Bedrock inference (generation) model ID."
  type        = string
  default     = "anthropic.claude-3-haiku-20240307-v1:0"
}

variable "bedrock_embedding_model_id" {
  description = "Bedrock embedding model ID (produces 1536-dim vectors)."
  type        = string
  default     = "amazon.titan-embed-text-v1"
}

variable "bedrock_model_override" {
  description = "Optional Bedrock model ID override for production tuning without code changes. Empty string means no override."
  type        = string
  default     = ""
}

# ---------------------------------------------------------------------------
# Data-tier sizing (Requirement 11.2)
# ---------------------------------------------------------------------------

variable "redis_node_type" {
  description = "ElastiCache Redis node type (e.g. cache.t4g.small, cache.r6g.large)."
  type        = string
  default     = "cache.t4g.small"
}

variable "opensearch_capacity" {
  description = "OpenSearch Serverless capacity in OCUs for indexing and search."
  type = object({
    indexing_ocu = number
    search_ocu   = number
  })
  default = {
    indexing_ocu = 2
    search_ocu   = 2
  }
}

# ---------------------------------------------------------------------------
# Networking (Requirement 11.1)
# ---------------------------------------------------------------------------

variable "vpc_cidr" {
  description = "IPv4 CIDR block for the VPC."
  type        = string
  default     = "10.0.0.0/16"

  validation {
    condition     = can(cidrhost(var.vpc_cidr, 0))
    error_message = "vpc_cidr must be a valid IPv4 CIDR block."
  }
}

variable "az_count" {
  description = "Number of availability zones to spread private subnets across."
  type        = number
  default     = 2

  validation {
    condition     = var.az_count >= 2 && var.az_count <= 3
    error_message = "az_count must be between 2 and 3."
  }
}

variable "tags" {
  description = "Additional tags applied to all resources."
  type        = map(string)
  default     = {}
}
