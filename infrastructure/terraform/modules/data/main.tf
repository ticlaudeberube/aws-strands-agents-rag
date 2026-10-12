# Data child module (task 14.1).
#
# Provisions the serverless data tier:
#   - Two DynamoDB tables (session + analytics), PAY_PER_REQUEST + TTL on `ttl`
#     (Requirements 11.1, 11.6)
#   - An OpenSearch Serverless VECTORSEARCH collection ("rag-vectors") with its
#     encryption, network (VPC-only), and data-access policies
#     (Requirements 4.1, 4.3, 4.5, 4.6, 3.3)
#   - An ElastiCache Redis replication group (TLS in transit) in the networking
#     private subnets (Requirements 3.3, 11.1)
#
# NOTE ON OPENSEARCH INDEXES (Requirements 4.1, 4.3, 4.6, 3.3):
# The two logical indexes used by the application —
#   * `rag-kb`    : knowledge-base document vectors
#   * `rag-cache` : the Layer-4 semantic response cache
# are NOT created here. OpenSearch Serverless does not support defining index
# mappings/settings (knn_vector field, HNSW parameters) through Terraform. The
# application creates both indexes at runtime via
# `OpenSearchClient.ensure_indexes()` with 768-dim cosine vectors and HNSW
# `m=30`, `ef_construction=200`. The Terraform layer provisions the collection,
# its security/access policies, and the VPC-endpoint association that make the
# collection reachable (and VPC-private) so that app-layer index creation and
# querying can satisfy Requirements 4.1, 4.3, 4.6, and 3.3.

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.79"
    }
  }
}

data "aws_caller_identity" "current" {}

locals {
  session_table_name   = "${var.name_prefix}-${var.session_table_name}"
  analytics_table_name = "${var.name_prefix}-${var.analytics_table_name}"
}

# ---------------------------------------------------------------------------
# DynamoDB — session table (conversation history)
#   PK session_id (String), SK timestamp (Number); PAY_PER_REQUEST; TTL on `ttl`
# ---------------------------------------------------------------------------
resource "aws_dynamodb_table" "session" {
  name         = local.session_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "session_id"
  range_key    = "timestamp"

  attribute {
    name = "session_id"
    type = "S"
  }

  attribute {
    name = "timestamp"
    type = "N"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = merge(var.tags, { Name = local.session_table_name })
}

# ---------------------------------------------------------------------------
# DynamoDB — analytics table (indexing dedup + audit)
#   PK doc_key (String), SK etag (String); PAY_PER_REQUEST; TTL on `ttl`
# ---------------------------------------------------------------------------
resource "aws_dynamodb_table" "analytics" {
  name         = local.analytics_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "doc_key"
  range_key    = "etag"

  attribute {
    name = "doc_key"
    type = "S"
  }

  attribute {
    name = "etag"
    type = "S"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = merge(var.tags, { Name = local.analytics_table_name })
}

# ---------------------------------------------------------------------------
# OpenSearch Serverless — encryption policy (required before the collection)
# ---------------------------------------------------------------------------
resource "aws_opensearchserverless_security_policy" "encryption" {
  name        = "${substr(var.collection_name, 0, 20)}-enc"
  type        = "encryption"
  description = "Encryption policy for the ${var.collection_name} collection."

  policy = jsonencode({
    Rules = [
      {
        ResourceType = "collection"
        Resource     = ["collection/${var.collection_name}"]
      }
    ]
    AWSOwnedKey = true
  })
}

# ---------------------------------------------------------------------------
# OpenSearch Serverless — network policy (VPC-only, no public access)
#   AllowFromPublic = false + SourceVPCEs pins access to the aoss VPC endpoint
#   from the networking module (Requirement 4.5).
# ---------------------------------------------------------------------------
resource "aws_opensearchserverless_security_policy" "network" {
  name        = "${substr(var.collection_name, 0, 20)}-net"
  type        = "network"
  description = "VPC-only network policy for the ${var.collection_name} collection (no public access)."

  policy = jsonencode([
    {
      Description = "VPC-only access to the ${var.collection_name} collection endpoint."
      Rules = [
        {
          ResourceType = "collection"
          Resource     = ["collection/${var.collection_name}"]
        }
      ]
      AllowFromPublic = false
      SourceVPCEs     = [var.aoss_vpc_endpoint_id]
    }
  ])
}

# ---------------------------------------------------------------------------
# OpenSearch Serverless — VECTORSEARCH collection ("rag-vectors")
#   768-dim cosine HNSW (m=30, ef_construction=200) indexes rag-kb / rag-cache
#   are created at the app layer (see header note). Requirements 4.1, 4.3, 4.6.
# ---------------------------------------------------------------------------
resource "aws_opensearchserverless_collection" "rag_vectors" {
  name        = var.collection_name
  type        = "VECTORSEARCH"
  description = "RAG vector collection; holds the rag-kb and rag-cache indexes created at runtime by the application."

  tags = merge(var.tags, { Name = var.collection_name })

  # Encryption and network policies must exist before the collection is usable.
  depends_on = [
    aws_opensearchserverless_security_policy.encryption,
    aws_opensearchserverless_security_policy.network,
  ]
}

# ---------------------------------------------------------------------------
# OpenSearch Serverless — data access policy
#   Grants the deploying principal full collection + index data permissions so
#   the application (and the Lambda role, added in task 15) can create the
#   rag-kb / rag-cache indexes and read/write documents.
# ---------------------------------------------------------------------------
resource "aws_opensearchserverless_access_policy" "data" {
  name        = "${substr(var.collection_name, 0, 20)}-data"
  type        = "data"
  description = "Data access policy for the ${var.collection_name} collection and its indexes."

  policy = jsonencode([
    {
      Rules = [
        {
          ResourceType = "index"
          Resource     = ["index/${var.collection_name}/*"]
          Permission   = ["aoss:*"]
        },
        {
          ResourceType = "collection"
          Resource     = ["collection/${var.collection_name}"]
          Permission   = ["aoss:*"]
        }
      ]
      Principal = [data.aws_caller_identity.current.arn]
    }
  ])
}

# ---------------------------------------------------------------------------
# ElastiCache — subnet group across the networking private subnets
# ---------------------------------------------------------------------------
resource "aws_elasticache_subnet_group" "redis" {
  name        = "${var.name_prefix}-redis-subnets"
  description = "Private subnets for the ${var.name_prefix} Redis replication group."
  subnet_ids  = var.private_subnet_ids

  tags = merge(var.tags, { Name = "${var.name_prefix}-redis-subnets" })
}

# ---------------------------------------------------------------------------
# ElastiCache — Redis replication group (TLS in transit, 3-node by default)
#   Layer-2 embedding cache + Layer-3 search-result cache (Requirement 3.3).
# ---------------------------------------------------------------------------
resource "aws_elasticache_replication_group" "redis" {
  replication_group_id = "${var.name_prefix}-redis"
  description          = "Distributed L2/L3 cache for ${var.name_prefix} (embeddings + search results)."

  engine         = "redis"
  engine_version = var.redis_engine_version
  node_type      = var.redis_node_type
  port           = 6379

  num_cache_clusters         = var.redis_num_cache_clusters
  automatic_failover_enabled = var.redis_num_cache_clusters > 1
  multi_az_enabled           = var.redis_num_cache_clusters > 1

  subnet_group_name  = aws_elasticache_subnet_group.redis.name
  security_group_ids = [var.redis_security_group_id]

  # TLS in transit + encryption at rest (Requirement 3.3 / security).
  transit_encryption_enabled = true
  at_rest_encryption_enabled = true

  tags = merge(var.tags, { Name = "${var.name_prefix}-redis" })
}
