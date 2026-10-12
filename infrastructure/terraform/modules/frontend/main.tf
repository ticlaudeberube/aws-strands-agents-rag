# Frontend child module (task 17.1).
#
# Composes:
#   - aws_s3_bucket (S3_Document_Bucket): versioned, SSE-encrypted, fully
#     private. Holds both documents/ (indexing input, Req 9.1) and frontend/
#     (React build, Req 8.1).
#   - aws_cloudfront_origin_access_control + bucket policy: lets ONLY this
#     distribution read the frontend/ objects (no public bucket access).
#   - aws_cloudfront_response_headers_policy: injects Cache-Control: no-store
#     on index.html so new deploys are picked up immediately (Req 8.3).
#   - aws_cloudfront_distribution: HTTPS-only (Req 8.2), 86400s default TTL for
#     static assets (Req 8.3), a dedicated /index.html behavior with 0 TTLs +
#     no-store, and SPA fallback (403/404 -> /index.html 200) for client-side
#     routing (Req 8.5).

# ---------------------------------------------------------------------------
# S3_Document_Bucket (Req 8.1 / 9.1)
# ---------------------------------------------------------------------------
resource "aws_s3_bucket" "documents" {
  bucket = "${var.name_prefix}-documents"

  tags = var.tags
}

# Versioning (Req 8.1 — versioned bucket).
resource "aws_s3_bucket_versioning" "documents" {
  bucket = aws_s3_bucket.documents.id

  versioning_configuration {
    status = "Enabled"
  }
}

# Server-side encryption at rest (Req 8.1 — SSE).
resource "aws_s3_bucket_server_side_encryption_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

# Block ALL public access — CloudFront reads via Origin Access Control only.
resource "aws_s3_bucket_public_access_block" "documents" {
  bucket = aws_s3_bucket.documents.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ---------------------------------------------------------------------------
# CloudFront Origin Access Control (OAC) — SigV4 signed requests to S3.
# ---------------------------------------------------------------------------
resource "aws_cloudfront_origin_access_control" "frontend" {
  name                              = "${var.name_prefix}-frontend-oac"
  description                       = "OAC for ${var.name_prefix} frontend S3 origin"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# ---------------------------------------------------------------------------
# Response headers policy — force Cache-Control: no-store on index.html so
# fresh deployments are reflected immediately (Req 8.3).
# ---------------------------------------------------------------------------
resource "aws_cloudfront_response_headers_policy" "no_store" {
  name    = "${var.name_prefix}-index-no-store"
  comment = "Cache-Control: no-store for index.html (fresh-deploy freshness, Req 8.3)"

  custom_headers_config {
    items {
      header   = "Cache-Control"
      value    = "no-store"
      override = true
    }
  }
}

# ---------------------------------------------------------------------------
# CloudFront distribution serving the frontend/ prefix as the SPA.
# ---------------------------------------------------------------------------
resource "aws_cloudfront_distribution" "frontend" {
  enabled             = true
  is_ipv6_enabled     = true
  comment             = "${var.name_prefix} React SPA"
  default_root_object = "index.html"
  price_class         = var.price_class

  origin {
    domain_name              = aws_s3_bucket.documents.bucket_regional_domain_name
    origin_id                = "s3-frontend"
    origin_access_control_id = aws_cloudfront_origin_access_control.frontend.id

    # Serve only the frontend/ prefix of the shared bucket as the web root
    # (Req 8.1); documents/ is never exposed through the distribution.
    origin_path = "/${var.frontend_prefix}"
  }

  # Default behavior: static assets, HTTPS-only, 24h default TTL (Req 8.2/8.3).
  default_cache_behavior {
    target_origin_id       = "s3-frontend"
    viewer_protocol_policy = "redirect-to-https"

    allowed_methods = ["GET", "HEAD", "OPTIONS"]
    cached_methods  = ["GET", "HEAD"]

    compress = true

    min_ttl     = 0
    default_ttl = var.default_ttl
    max_ttl     = var.max_ttl

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }
  }

  # index.html behavior: never cache (TTLs 0 + no-store header) so the latest
  # deployment is always served (Req 8.3).
  ordered_cache_behavior {
    path_pattern           = "/index.html"
    target_origin_id       = "s3-frontend"
    viewer_protocol_policy = "redirect-to-https"

    allowed_methods = ["GET", "HEAD", "OPTIONS"]
    cached_methods  = ["GET", "HEAD"]

    compress = true

    min_ttl     = 0
    default_ttl = 0
    max_ttl     = 0

    response_headers_policy_id = aws_cloudfront_response_headers_policy.no_store.id

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }
  }

  # SPA client-side routing: any non-asset path that S3 answers with 403/404
  # is rewritten to index.html with a 200 so React Router can resolve it
  # (Req 8.5).
  custom_error_response {
    error_code            = 403
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 0
  }

  custom_error_response {
    error_code            = 404
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 0
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = var.tags
}

# ---------------------------------------------------------------------------
# Bucket policy — grant ONLY this CloudFront distribution read access to the
# frontend/ objects (scoped to the frontend prefix). Public access stays
# blocked; CloudFront authenticates with SigV4 via the OAC.
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "frontend_oac" {
  statement {
    sid    = "AllowCloudFrontReadFrontend"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.documents.arn}/${var.frontend_prefix}/*"]

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.frontend.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "frontend_oac" {
  bucket = aws_s3_bucket.documents.id
  policy = data.aws_iam_policy_document.frontend_oac.json

  # Ensure public-access-block is in place before attaching the policy.
  depends_on = [aws_s3_bucket_public_access_block.documents]
}
