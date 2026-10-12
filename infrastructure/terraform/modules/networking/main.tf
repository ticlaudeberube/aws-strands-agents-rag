# Networking child module (task 13.1).
#
# Provides the VPC foundation for the serverless stack:
#   - VPC + private subnets across AZs (via the official registry VPC module)
#   - Security groups for Lambda, Redis, and VPC interface endpoints
#   - VPC endpoints: OpenSearch Serverless (aoss) + Bedrock runtime +
#     Secrets Manager (interface), and S3 + DynamoDB (gateway)
#
# OpenSearch Serverless and ElastiCache Redis live in private subnets with no
# public internet access (Requirements 4.5, 11.1, 11.4).

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.79"
    }
  }
}

data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  azs = slice(data.aws_availability_zones.available.names, 0, var.az_count)

  # Carve one /20 private subnet per AZ out of the VPC CIDR.
  private_subnet_cidrs = [
    for i in range(var.az_count) : cidrsubnet(var.vpc_cidr, 4, i)
  ]
}

# ---------------------------------------------------------------------------
# VPC + private subnets (official terraform-aws-modules/vpc/aws, pinned 5.x)
# ---------------------------------------------------------------------------
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.21"

  name = "${var.name_prefix}-vpc"
  cidr = var.vpc_cidr

  azs             = local.azs
  private_subnets = local.private_subnet_cidrs

  # Private-only network: Lambda, Redis, and OpenSearch reach AWS services
  # through VPC endpoints, so no public subnets / NAT / IGW are provisioned.
  enable_nat_gateway = false
  create_igw         = false

  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = var.tags
}

# ---------------------------------------------------------------------------
# Security groups
# ---------------------------------------------------------------------------

# Lambda functions attached to the private subnets.
resource "aws_security_group" "lambda" {
  name        = "${var.name_prefix}-lambda-sg"
  description = "Security group for Lambda functions in private subnets"
  vpc_id      = module.vpc.vpc_id

  # Lambda needs outbound to reach Redis, VPC endpoints, and AWS APIs.
  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-lambda-sg" })
}

# ElastiCache Redis cluster.
resource "aws_security_group" "redis" {
  name        = "${var.name_prefix}-redis-sg"
  description = "Security group for ElastiCache Redis"
  vpc_id      = module.vpc.vpc_id

  ingress {
    description     = "Redis from Lambda"
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.lambda.id]
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-redis-sg" })
}

# VPC interface endpoints (aoss, bedrock-runtime, secretsmanager).
resource "aws_security_group" "vpc_endpoints" {
  name        = "${var.name_prefix}-vpce-sg"
  description = "Security group for VPC interface endpoints"
  vpc_id      = module.vpc.vpc_id

  ingress {
    description     = "HTTPS from Lambda"
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    security_groups = [aws_security_group.lambda.id]
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-vpce-sg" })
}

# ---------------------------------------------------------------------------
# Interface VPC endpoints (OpenSearch Serverless, Bedrock runtime, Secrets Mgr)
# ---------------------------------------------------------------------------
resource "aws_vpc_endpoint" "aoss" {
  vpc_id              = module.vpc.vpc_id
  service_name        = "com.amazonaws.${var.aws_region}.aoss"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = module.vpc.private_subnets
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  private_dns_enabled = true

  tags = merge(var.tags, { Name = "${var.name_prefix}-aoss-vpce" })
}

resource "aws_vpc_endpoint" "bedrock_runtime" {
  vpc_id              = module.vpc.vpc_id
  service_name        = "com.amazonaws.${var.aws_region}.bedrock-runtime"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = module.vpc.private_subnets
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  private_dns_enabled = true

  tags = merge(var.tags, { Name = "${var.name_prefix}-bedrock-runtime-vpce" })
}

resource "aws_vpc_endpoint" "secretsmanager" {
  vpc_id              = module.vpc.vpc_id
  service_name        = "com.amazonaws.${var.aws_region}.secretsmanager"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = module.vpc.private_subnets
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  private_dns_enabled = true

  tags = merge(var.tags, { Name = "${var.name_prefix}-secretsmanager-vpce" })
}

# ---------------------------------------------------------------------------
# Gateway VPC endpoints (S3, DynamoDB) attached to private route tables
# ---------------------------------------------------------------------------
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = module.vpc.vpc_id
  service_name      = "com.amazonaws.${var.aws_region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = module.vpc.private_route_table_ids

  tags = merge(var.tags, { Name = "${var.name_prefix}-s3-vpce" })
}

resource "aws_vpc_endpoint" "dynamodb" {
  vpc_id            = module.vpc.vpc_id
  service_name      = "com.amazonaws.${var.aws_region}.dynamodb"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = module.vpc.private_route_table_ids

  tags = merge(var.tags, { Name = "${var.name_prefix}-dynamodb-vpce" })
}
