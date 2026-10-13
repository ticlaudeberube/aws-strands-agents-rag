# Production environment values.
stage      = "prod"
aws_region = "us-east-1"

bedrock_inference_model_id = "amazon.nova-lite-v1:0"
bedrock_embedding_model_id = "amazon.titan-embed-text-v1"
bedrock_model_override     = "amazon.nova-pro-v1:0"

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
