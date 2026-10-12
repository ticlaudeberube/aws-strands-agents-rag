# Frontend child module input variables (task 17.1).
#
# This module provisions the serverless static edge: a single versioned,
# SSE-encrypted, fully-private S3 bucket (the S3_Document_Bucket) that holds
# BOTH the source documents under `documents/` (indexing pipeline input, Req 9.1)
# AND the React build under `frontend/` (Req 8.1), plus a CloudFront
# distribution that serves the `frontend/` prefix as the SPA over HTTPS-only
# (Req 8.2), with a 24h default TTL for static assets, `no-store` for
# index.html (Req 8.3), and SPA fallback routing to index.html (Req 8.5).

variable "name_prefix" {
  description = "Resource name prefix (e.g. strands-rag-dev). Used to derive the S3 bucket name."
  type        = string
}

variable "frontend_prefix" {
  description = "S3 key prefix (CloudFront origin path) that holds the React build artifacts (Req 8.1)."
  type        = string
  default     = "frontend"
}

variable "default_ttl" {
  description = "CloudFront default TTL (seconds) for static assets (Req 8.3)."
  type        = number
  default     = 86400
}

variable "max_ttl" {
  description = "CloudFront maximum TTL (seconds) for static assets."
  type        = number
  default     = 31536000
}

variable "price_class" {
  description = "CloudFront price class controlling edge-location coverage."
  type        = string
  default     = "PriceClass_100"
}

variable "tags" {
  description = "Tags applied to all resources in this module."
  type        = map(string)
  default     = {}
}
