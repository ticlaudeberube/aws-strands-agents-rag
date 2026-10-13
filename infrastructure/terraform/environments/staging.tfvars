# Staging environment values.
stage      = "staging"
aws_region = "us-east-1"

bedrock_inference_model_id = "amazon.nova-lite-v1:0"
bedrock_embedding_model_id = "amazon.titan-embed-text-v1"
bedrock_model_override     = ""

redis_node_type = "cache.t4g.medium"

opensearch_capacity = {
  indexing_ocu = 4
  search_ocu   = 4
}

vpc_cidr = "10.1.0.0/16"
az_count = 2

tags = {
  CostCenter = "rag-staging"
}
