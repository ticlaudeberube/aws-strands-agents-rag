# API child module input variables (task 16.1).
#
# This module provisions the serverless edge: an API Gateway v2 (HTTP API)
# exposing POST /chat (Lambda proxy, Cognito-JWT protected) and GET /health
# (MOCK integration, no Lambda), a Cognito user pool + client, a WAFv2
# rate-limit web ACL, and the stage-level throttling that enforces the
# 100 rps limit (Req 6.4).

variable "name_prefix" {
  description = "Resource name prefix (e.g. strands-rag-dev)."
  type        = string
}

variable "aws_region" {
  description = "AWS region. Used to build the Cognito JWT issuer URL."
  type        = string
}

# ---------------------------------------------------------------------------
# Chat Lambda wiring (Req 6.1)
# ---------------------------------------------------------------------------

variable "chat_function_name" {
  description = "Name of the chat handler Lambda function (for the invoke permission)."
  type        = string
}

variable "chat_function_arn" {
  description = "ARN of the chat handler Lambda function (source for the invoke permission)."
  type        = string
}

variable "chat_function_invoke_arn" {
  description = "Invoke ARN of the chat handler Lambda function (used as the AWS_PROXY integration URI)."
  type        = string
}

# ---------------------------------------------------------------------------
# CORS (Req 6.5)
# ---------------------------------------------------------------------------

variable "cors_allow_origin" {
  description = "The CloudFront origin allowed by CORS on the HTTP API. Defaults to '*' until the frontend module (task 17) supplies the CloudFront domain, at which point the root passes the exact https origin."
  type        = string
  default     = "*"
}

# ---------------------------------------------------------------------------
# Throttling / rate limiting (Req 6.4)
# ---------------------------------------------------------------------------

variable "throttling_rate_limit" {
  description = "API Gateway stage default route steady-state request rate limit (requests per second). Primary enforcement of Req 6.4 (100 rps)."
  type        = number
  default     = 100
}

variable "throttling_burst_limit" {
  description = "API Gateway stage default route burst limit (bucket capacity). Set to the rps limit so short bursts are absorbed without exceeding the steady-state rate."
  type        = number
  default     = 100
}

variable "tags" {
  description = "Tags applied to all resources in this module."
  type        = map(string)
  default     = {}
}
