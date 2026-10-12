# Root module outputs.
#
# For task 13.1 only the networking outputs are exposed. Later tasks (14-18)
# add api_gateway_url, cloudfront_domain, user_pool_id, etc.

output "vpc_id" {
  description = "The ID of the VPC."
  value       = module.networking.vpc_id
}

output "private_subnet_ids" {
  description = "List of private subnet IDs (Lambda + Redis)."
  value       = module.networking.private_subnet_ids
}

output "security_group_ids" {
  description = "Map of security group IDs for Lambda, Redis, and VPC endpoints."
  value       = module.networking.security_group_ids
}

output "vpc_endpoint_ids" {
  description = "Map of VPC endpoint IDs (aoss, bedrock-runtime, s3, dynamodb, secretsmanager)."
  value       = module.networking.vpc_endpoint_ids
}

# ---------------------------------------------------------------------------
# Data tier (task 14.1)
# ---------------------------------------------------------------------------

output "session_table_name" {
  description = "Name of the DynamoDB session table."
  value       = module.data.session_table_name
}

output "analytics_table_name" {
  description = "Name of the DynamoDB analytics table."
  value       = module.data.analytics_table_name
}

output "opensearch_collection_endpoint" {
  description = "OpenSearch Serverless collection endpoint (rag-kb / rag-cache indexes created at the app layer)."
  value       = module.data.opensearch_collection_endpoint
}

output "redis_primary_endpoint" {
  description = "Primary (write) endpoint address of the Redis replication group."
  value       = module.data.redis_primary_endpoint
}

output "redis_reader_endpoint" {
  description = "Reader (read) endpoint address of the Redis replication group."
  value       = module.data.redis_reader_endpoint
}

# ---------------------------------------------------------------------------
# Compute tier (task 15.1)
# ---------------------------------------------------------------------------

output "chat_function_arn" {
  description = "ARN of the chat handler Lambda function."
  value       = module.compute.chat_function_arn
}

output "chat_function_name" {
  description = "Name of the chat handler Lambda function."
  value       = module.compute.chat_function_name
}

output "indexing_function_arn" {
  description = "ARN of the indexing handler Lambda function."
  value       = module.compute.indexing_function_arn
}

output "indexing_function_name" {
  description = "Name of the indexing handler Lambda function."
  value       = module.compute.indexing_function_name
}

output "lambda_role_arn" {
  description = "ARN of the shared Lambda execution IAM role."
  value       = module.compute.lambda_role_arn
}

# ---------------------------------------------------------------------------
# API tier (task 16.1)
# ---------------------------------------------------------------------------

output "api_endpoint" {
  description = "Base invoke URL of the HTTP API ($default stage). POST /chat and GET /health are served from here."
  value       = module.api.api_endpoint
}

output "user_pool_id" {
  description = "ID of the Cognito user pool backing the API JWT authorizer."
  value       = module.api.user_pool_id
}

output "user_pool_client_id" {
  description = "ID of the Cognito user pool app client (JWT audience)."
  value       = module.api.user_pool_client_id
}

# ---------------------------------------------------------------------------
# Frontend tier (task 17.1)
# ---------------------------------------------------------------------------

output "cloudfront_domain" {
  description = "CloudFront distribution domain name serving the React SPA over HTTPS."
  value       = module.frontend.cloudfront_domain
}

output "documents_bucket_id" {
  description = "Name of the shared S3 bucket holding source documents (documents/) and the React build (frontend/)."
  value       = module.frontend.documents_bucket_id
}

# ---------------------------------------------------------------------------
# Observability tier (task 18.1)
# ---------------------------------------------------------------------------

output "errors_total_alarm_arn" {
  description = "ARN of the errors/total CloudWatch metric alarm (Sum > 10 in 5 minutes; Req 12.3)."
  value       = module.observability.errors_total_alarm_arn
}

output "observability_metric_namespace" {
  description = "CloudWatch metric namespace the errors/total alarm watches (StrandsRAG/<stage>), matching the Lambda MetricsEmitter."
  value       = module.observability.metric_namespace
}

output "lambda_log_group_names" {
  description = "CloudWatch log group names for the chat and indexing Lambda functions."
  value       = module.observability.log_group_names
}

output "alarm_sns_topic_arn" {
  description = "ARN of the optional alarm-notification SNS topic (null unless enabled on the observability module)."
  value       = module.observability.alarm_sns_topic_arn
}
