# Frontend child module outputs (task 17.1).

output "documents_bucket_id" {
  description = "Name/id of the shared S3 documents bucket (holds documents/ and frontend/). Wired into the compute module to enable the S3 ObjectCreated indexing trigger (Req 9.1)."
  value       = aws_s3_bucket.documents.id
}

output "documents_bucket_arn" {
  description = "ARN of the shared S3 documents bucket. Wired into the compute module for the S3 trigger and scoped S3 read IAM policy."
  value       = aws_s3_bucket.documents.arn
}

output "cloudfront_domain" {
  description = "CloudFront distribution domain name (e.g. dxxxx.cloudfront.net). Used to build the CORS origin for the api module."
  value       = aws_cloudfront_distribution.frontend.domain_name
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID (used for cache invalidations on deploy)."
  value       = aws_cloudfront_distribution.frontend.id
}
