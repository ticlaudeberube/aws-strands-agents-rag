# Data child module outputs (task 14.1).

output "session_table_name" {
  description = "Name of the DynamoDB session table."
  value       = aws_dynamodb_table.session.name
}

output "session_table_arn" {
  description = "ARN of the DynamoDB session table."
  value       = aws_dynamodb_table.session.arn
}

output "analytics_table_name" {
  description = "Name of the DynamoDB analytics table."
  value       = aws_dynamodb_table.analytics.name
}

output "analytics_table_arn" {
  description = "ARN of the DynamoDB analytics table."
  value       = aws_dynamodb_table.analytics.arn
}

output "opensearch_collection_name" {
  description = "Name of the OpenSearch Serverless VECTORSEARCH collection."
  value       = aws_opensearchserverless_collection.rag_vectors.name
}

output "opensearch_collection_arn" {
  description = "ARN of the OpenSearch Serverless collection."
  value       = aws_opensearchserverless_collection.rag_vectors.arn
}

output "opensearch_collection_endpoint" {
  description = "Collection endpoint for index/search/data-upload requests (used by the app-layer OpenSearchClient)."
  value       = aws_opensearchserverless_collection.rag_vectors.collection_endpoint
}

output "redis_primary_endpoint" {
  description = "Primary (write) endpoint address of the Redis replication group."
  value       = aws_elasticache_replication_group.redis.primary_endpoint_address
}

output "redis_reader_endpoint" {
  description = "Reader (read) endpoint address of the Redis replication group."
  value       = aws_elasticache_replication_group.redis.reader_endpoint_address
}

output "redis_port" {
  description = "Port the Redis replication group listens on."
  value       = aws_elasticache_replication_group.redis.port
}
