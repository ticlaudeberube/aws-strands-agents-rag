variable "name_prefix" {
  description = "Prefix applied to resource names (e.g. strands-rag-dev)."
  type        = string
}

variable "aws_region" {
  description = "AWS region (used to build VPC endpoint service names)."
  type        = string
}

variable "vpc_cidr" {
  description = "IPv4 CIDR block for the VPC."
  type        = string
}

variable "az_count" {
  description = "Number of availability zones to spread private subnets across."
  type        = number
  default     = 2
}

variable "tags" {
  description = "Tags applied to all networking resources."
  type        = map(string)
  default     = {}
}
