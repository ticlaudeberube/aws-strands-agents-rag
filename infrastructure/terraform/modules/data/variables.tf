# Data child module input variables (task 14.1).

variable "name_prefix" {
  description = "Prefix applied to resource names (e.g. strands-rag-dev)."
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs (from networking) for the ElastiCache subnet group."
  type        = list(string)
}

variable "redis_security_group_id" {
  description = "Security group ID (from networking) controlling access to ElastiCache Redis."
  type        = string
}

variable "aoss_vpc_endpoint_id" {
  description = "VPC interface endpoint ID for OpenSearch Serverless (aoss), from networking. Used by the collection network policy so the collection is reachable only from inside the VPC (Requirement 4.5)."
  type        = string
}

# ---------------------------------------------------------------------------
# OpenSearch Serverless collection naming
# ---------------------------------------------------------------------------
# AOSS collection names must be 3-32 chars, lowercase letters/numbers/hyphens,
# and start with a lowercase letter. The design calls the collection
# "rag-vectors"; we keep that name (optionally stage-suffixed) within limits.
variable "collection_name" {
  description = "Name of the OpenSearch Serverless VECTORSEARCH collection (3-32 lowercase chars). The logical rag-kb and rag-cache indexes live inside this single collection."
  type        = string
  default     = "rag-vectors"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,31}$", var.collection_name))
    error_message = "collection_name must be 3-32 chars, lowercase alphanumeric or hyphen, and start with a letter."
  }
}

# ---------------------------------------------------------------------------
# DynamoDB table name prefixes (Requirement 11.6)
# ---------------------------------------------------------------------------
variable "session_table_name" {
  description = "Name of the DynamoDB session table (conversation history)."
  type        = string
  default     = "sessions"
}

variable "analytics_table_name" {
  description = "Name of the DynamoDB analytics table (indexing dedup/audit)."
  type        = string
  default     = "analytics"
}

# ---------------------------------------------------------------------------
# ElastiCache Redis sizing (Requirement 3.3)
# ---------------------------------------------------------------------------
variable "redis_node_type" {
  description = "ElastiCache Redis node type (e.g. cache.t4g.small, cache.r6g.large)."
  type        = string
  default     = "cache.t4g.small"
}

variable "redis_num_cache_clusters" {
  description = "Number of Redis cache clusters (primary + replicas). Design calls for a 3-node cluster (1 primary + 2 replicas)."
  type        = number
  default     = 3

  validation {
    condition     = var.redis_num_cache_clusters >= 1 && var.redis_num_cache_clusters <= 6
    error_message = "redis_num_cache_clusters must be between 1 and 6."
  }
}

variable "redis_engine_version" {
  description = "Redis engine version. 7.x is required so transit encryption can be toggled without forcing replacement."
  type        = string
  default     = "7.1"
}

variable "tags" {
  description = "Tags applied to all data-tier resources."
  type        = map(string)
  default     = {}
}
