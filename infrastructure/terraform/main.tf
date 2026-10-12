# Root module composition.
#
# This root module wires together the serverless stack from focused child
# modules. For task 13.1 only the `networking` module is composed; the data,
# compute, api, frontend, and observability modules are added by later tasks
# (14-18) at the clearly-marked placeholders below.

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = merge(
      {
        Project     = "strands-rag"
        Environment = var.stage
        ManagedBy   = "terraform"
      },
      var.tags,
    )
  }
}

locals {
  name_prefix = "strands-rag-${var.stage}"

  common_tags = merge(
    {
      Project     = "strands-rag"
      Environment = var.stage
      ManagedBy   = "terraform"
    },
    var.tags,
  )
}

# ---------------------------------------------------------------------------
# Networking (task 13.1) — VPC, private subnets, VPC endpoints, security groups
# ---------------------------------------------------------------------------
module "networking" {
  source = "./modules/networking"

  name_prefix = local.name_prefix
  aws_region  = var.aws_region
  vpc_cidr    = var.vpc_cidr
  az_count    = var.az_count

  tags = local.common_tags
}

# ---------------------------------------------------------------------------
# Data (task 14.1) — DynamoDB tables, OpenSearch Serverless collection, and
# ElastiCache Redis in the networking private subnets.
# ---------------------------------------------------------------------------
module "data" {
  source = "./modules/data"

  name_prefix             = local.name_prefix
  private_subnet_ids      = module.networking.private_subnet_ids
  redis_security_group_id = module.networking.redis_security_group_id
  aoss_vpc_endpoint_id    = module.networking.vpc_endpoint_ids["aoss"]

  redis_node_type = var.redis_node_type

  tags = local.common_tags
}

# ---------------------------------------------------------------------------
# Compute (task 15.1) — Lambda chat + indexing functions and the least-privilege
# IAM role/policies, VPC-attached to networking private subnets, wired to the
# data-tier outputs. The S3 ObjectCreated trigger (Req 9.1) is enabled once the
# frontend module (task 17) supplies the documents bucket id/arn below.
# ---------------------------------------------------------------------------
module "compute" {
  source = "./modules/compute"

  name_prefix = local.name_prefix

  # Networking (Req 11.4)
  private_subnet_ids       = module.networking.private_subnet_ids
  lambda_security_group_id = module.networking.lambda_security_group_id

  # Data tier
  session_table_name             = module.data.session_table_name
  session_table_arn              = module.data.session_table_arn
  analytics_table_name           = module.data.analytics_table_name
  analytics_table_arn            = module.data.analytics_table_arn
  opensearch_collection_arn      = module.data.opensearch_collection_arn
  opensearch_collection_endpoint = module.data.opensearch_collection_endpoint
  redis_primary_endpoint         = module.data.redis_primary_endpoint
  redis_port                     = module.data.redis_port

  # Bedrock model configuration (Req 5.x)
  bedrock_inference_model_id = var.bedrock_inference_model_id
  bedrock_embedding_model_id = var.bedrock_embedding_model_id
  bedrock_model_override     = var.bedrock_model_override

  # S3 documents bucket from the frontend module (task 17). Wiring these in
  # activates the compute S3 ObjectCreated trigger for the indexing Lambda
  # (Req 9.1). This creates a compute -> frontend dependency, which is safe:
  # the frontend module does not depend on compute, so there is no cycle.
  documents_bucket_id  = module.frontend.documents_bucket_id
  documents_bucket_arn = module.frontend.documents_bucket_arn

  tags = local.common_tags
}

# ---------------------------------------------------------------------------
# API (task 16.1) — API Gateway v2 HTTP API (POST /chat Lambda proxy,
# GET /health MOCK), Cognito user pool + JWT authorizer, CORS, stage
# throttling (100 rps), and a WAFv2 rate-limit web ACL on the stage.
# ---------------------------------------------------------------------------
module "api" {
  source = "./modules/api"

  name_prefix = local.name_prefix
  aws_region  = var.aws_region

  # Chat Lambda from the compute module (Req 6.1).
  chat_function_name       = module.compute.chat_function_name
  chat_function_arn        = module.compute.chat_function_arn
  chat_function_invoke_arn = module.compute.chat_function_invoke_arn

  # CORS origin (Req 6.5). Set to the exact https CloudFront origin supplied by
  # the frontend module (task 17).
  cors_allow_origin = "https://${module.frontend.cloudfront_domain}"

  tags = local.common_tags
}

# ---------------------------------------------------------------------------
# Frontend (task 17.1) — the shared S3 documents bucket (documents/ + frontend/)
# and a CloudFront distribution serving the frontend/ prefix as the SPA
# (HTTPS-only, 86400s default TTL, no-store index.html, SPA fallback routing).
# This module has no dependencies on compute/api, so wiring its outputs into
# those modules introduces no dependency cycle.
# ---------------------------------------------------------------------------
module "frontend" {
  source = "./modules/frontend"

  name_prefix = local.name_prefix

  tags = local.common_tags
}

# ---------------------------------------------------------------------------
# Observability (task 18.1) — CloudWatch log groups per Lambda, the
# errors/total > 10-in-5-minutes alarm (Req 12.3), and X-Ray active tracing
# (Req 12.4, already enabled on the Lambdas in the compute module). The alarm
# namespace is StrandsRAG/<stage> to match what the Lambda MetricsEmitter emits
# at runtime; `stage` (not name_prefix) is threaded through for that reason.
# ---------------------------------------------------------------------------
module "observability" {
  source = "./modules/observability"

  name_prefix = local.name_prefix
  stage       = var.stage

  # Lambda function names from the compute module (Req 11.1 / 12.3).
  chat_function_name     = module.compute.chat_function_name
  indexing_function_name = module.compute.indexing_function_name

  tags = local.common_tags
}
