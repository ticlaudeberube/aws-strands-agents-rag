# Development environment values.
stage      = "dev"
aws_region = "us-east-1"

bedrock_inference_model_id = "anthropic.claude-3-haiku-20240307-v1:0"
bedrock_embedding_model_id = "amazon.titan-embed-text-v1"
bedrock_model_override     = ""

redis_node_type = "cache.t4g.small"

opensearch_capacity = {
  indexing_ocu = 2
  search_ocu   = 2
}

vpc_cidr = "10.0.0.0/16"
az_count = 2

tags = {
  CostCenter = "rag-dev"
}
