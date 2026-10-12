output "vpc_id" {
  description = "The ID of the VPC."
  value       = module.vpc.vpc_id
}

output "private_subnet_ids" {
  description = "List of private subnet IDs (Lambda + Redis)."
  value       = module.vpc.private_subnets
}

output "private_route_table_ids" {
  description = "List of private route table IDs (used by gateway endpoints)."
  value       = module.vpc.private_route_table_ids
}

output "lambda_security_group_id" {
  description = "Security group ID for Lambda functions."
  value       = aws_security_group.lambda.id
}

output "redis_security_group_id" {
  description = "Security group ID for ElastiCache Redis."
  value       = aws_security_group.redis.id
}

output "vpc_endpoints_security_group_id" {
  description = "Security group ID for VPC interface endpoints."
  value       = aws_security_group.vpc_endpoints.id
}

output "security_group_ids" {
  description = "Map of all security group IDs (lambda, redis, vpc_endpoints)."
  value = {
    lambda        = aws_security_group.lambda.id
    redis         = aws_security_group.redis.id
    vpc_endpoints = aws_security_group.vpc_endpoints.id
  }
}

output "vpc_endpoint_ids" {
  description = "Map of VPC endpoint IDs."
  value = {
    aoss            = aws_vpc_endpoint.aoss.id
    bedrock_runtime = aws_vpc_endpoint.bedrock_runtime.id
    s3              = aws_vpc_endpoint.s3.id
    dynamodb        = aws_vpc_endpoint.dynamodb.id
    secretsmanager  = aws_vpc_endpoint.secretsmanager.id
  }
}
