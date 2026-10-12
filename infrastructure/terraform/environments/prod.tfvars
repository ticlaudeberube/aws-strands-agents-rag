# Production environment values.
stage      = "prod"
aws_region = "us-east-1"

# Override to a stronger generation model in production without code changes.
bedrock_inference_model_id = "anthropic.claude-3-haiku-20240307-v1:0"
bedrock_embedding_model_id = "amazon.titan-embed-text-v1"
bedrock_model_override     = "anthropic.claude-3-sonnet-20240229-v1:0"

redis_node_type = "cache.r6g.large"

opensearch_capacity = {
  indexing_ocu = 6
  search_ocu   = 6
}

vpc_cidr = "10.2.0.0/16"
az_count = 3

tags = {
  CostCenter = "rag-prod"
}
