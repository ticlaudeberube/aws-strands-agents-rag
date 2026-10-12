# API child module (task 16.1) — API Gateway v2 (HTTP API) + Cognito + WAF.
#
# Design choice: an HTTP API (aws_apigatewayv2_api, protocol HTTP) is used
# instead of a REST API because it has first-class JWT authorizers (native
# Cognito validation, no Lambda authorizer) and simpler built-in CORS.
#
# Endpoints:
#   POST /chat   -> AWS_PROXY integration to the chat Lambda (Req 6.1),
#                   protected by a JWT authorizer backed by the Cognito user
#                   pool (Req 6.3, 7.3). Missing/invalid/expired tokens are
#                   rejected by API Gateway with HTTP 401 before the Lambda
#                   is ever invoked.
#   GET  /health -> MOCK integration returning HTTP 200 {"status":"healthy"}
#                   WITHOUT invoking any Lambda (Req 6.2).
#
# Rate limiting (Req 6.4) is enforced primarily at the API Gateway stage via
# default route throttling (100 rps), with a WAFv2 rate-based rule as
# defense-in-depth.

# ---------------------------------------------------------------------------
# Cognito user pool (Req 7.1) + client (Req 7.2)
# ---------------------------------------------------------------------------

resource "aws_cognito_user_pool" "this" {
  name = "${var.name_prefix}-users"

  # Users sign up / sign in with their email address.
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  # Req 7.1: minimum length 12, require uppercase, require numbers (digits),
  # and require symbols (special characters).
  password_policy {
    minimum_length    = 12
    require_uppercase = true
    require_numbers   = true
    require_symbols   = true
    require_lowercase = true
  }

  tags = var.tags
}

resource "aws_cognito_user_pool_client" "this" {
  name         = "${var.name_prefix}-client"
  user_pool_id = aws_cognito_user_pool.this.id

  # Public SPA client — no client secret held in the browser (Req 7.4/7.5
  # keep the JWT in memory, not a server secret).
  generate_secret = false

  # Req 7.2: issue access tokens that expire after 1 hour.
  access_token_validity  = 1
  id_token_validity      = 1
  refresh_token_validity = 30

  token_validity_units {
    access_token  = "hours"
    id_token      = "hours"
    refresh_token = "days"
  }

  explicit_auth_flows = [
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
  ]

  # Enable token revocation so refresh tokens can be invalidated on sign-out.
  enable_token_revocation = true
}

# ---------------------------------------------------------------------------
# HTTP API (Req 6.1, 6.5)
# ---------------------------------------------------------------------------

resource "aws_apigatewayv2_api" "this" {
  name          = "${var.name_prefix}-http-api"
  protocol_type = "HTTP"

  # Req 6.5: CORS for the CloudFront origin, allowing Content-Type and
  # Authorization headers. GET (health) and POST (chat) plus OPTIONS preflight.
  cors_configuration {
    allow_origins = [var.cors_allow_origin]
    allow_methods = ["GET", "POST", "OPTIONS"]
    allow_headers = ["Content-Type", "Authorization"]
    max_age       = 3600
  }

  tags = var.tags
}

# JWT authorizer validating Cognito-issued tokens (Req 6.3, 7.3). The issuer
# is the Cognito user pool endpoint; the audience is the app client id.
resource "aws_apigatewayv2_authorizer" "cognito_jwt" {
  api_id           = aws_apigatewayv2_api.this.id
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]
  name             = "${var.name_prefix}-cognito-jwt"

  jwt_configuration {
    audience = [aws_cognito_user_pool_client.this.id]
    issuer   = "https://${aws_cognito_user_pool.this.endpoint}"
  }
}

# --- POST /chat : Lambda proxy integration (Req 6.1) -----------------------

resource "aws_apigatewayv2_integration" "chat" {
  api_id                 = aws_apigatewayv2_api.this.id
  integration_type       = "AWS_PROXY"
  integration_uri        = var.chat_function_invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "chat" {
  api_id    = aws_apigatewayv2_api.this.id
  route_key = "POST /chat"
  target    = "integrations/${aws_apigatewayv2_integration.chat.id}"

  # Req 6.3/7.3: unauthenticated or invalid-token requests are rejected with
  # HTTP 401 by the JWT authorizer before the Lambda integration runs.
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito_jwt.id
}

# Allow API Gateway to invoke the chat Lambda.
resource "aws_lambda_permission" "apigw_chat" {
  statement_id  = "AllowAPIGatewayInvokeChat"
  action        = "lambda:InvokeFunction"
  function_name = var.chat_function_name
  principal     = "apigateway.amazonaws.com"

  # Scope the permission to this API's /chat route on any stage.
  source_arn = "${aws_apigatewayv2_api.this.execution_arn}/*/*/chat"
}

# --- GET /health : MOCK integration, no Lambda (Req 6.2) -------------------
#
# A MOCK integration lets API Gateway return a canned 200 response without
# invoking any backend. The request template selects the 200 integration
# response; the response template emits the static healthy body.

resource "aws_apigatewayv2_integration" "health" {
  api_id           = aws_apigatewayv2_api.this.id
  integration_type = "MOCK"

  request_templates = {
    "application/json" = jsonencode({ statusCode = 200 })
  }

  template_selection_expression = "200"
}

resource "aws_apigatewayv2_integration_response" "health" {
  api_id                   = aws_apigatewayv2_api.this.id
  integration_id           = aws_apigatewayv2_integration.health.id
  integration_response_key = "/200/"

  response_templates = {
    "application/json" = jsonencode({ status = "healthy" })
  }
}

resource "aws_apigatewayv2_route" "health" {
  api_id    = aws_apigatewayv2_api.this.id
  route_key = "GET /health"
  target    = "integrations/${aws_apigatewayv2_integration.health.id}"

  # Public health check — no authorizer (Req 6.2).
  authorization_type = "NONE"
}

resource "aws_apigatewayv2_route_response" "health" {
  api_id             = aws_apigatewayv2_api.this.id
  route_id           = aws_apigatewayv2_route.health.id
  route_response_key = "$default"
}

# ---------------------------------------------------------------------------
# Stage with default-route throttling (Req 6.4 primary enforcement)
# ---------------------------------------------------------------------------

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.this.id
  name        = "$default"
  auto_deploy = true

  # Req 6.4: 100 requests/second steady-state with a matching burst bucket.
  # Requests exceeding this limit are throttled by API Gateway with HTTP 429.
  default_route_settings {
    throttling_rate_limit  = var.throttling_rate_limit
    throttling_burst_limit = var.throttling_burst_limit
  }

  tags = var.tags
}

# ---------------------------------------------------------------------------
# WAFv2 rate-based rule (Req 6.4 defense-in-depth)
# ---------------------------------------------------------------------------
#
# WAF rate-based rules count requests per source IP over a rolling 5-minute
# window (minimum window via evaluation_window_sec = 60s here). The stage-level
# throttling above is the primary "100 rps" enforcement; this web ACL is a
# secondary IP-based guard against abusive bursts/DDoS.
#
# Mapping Req 6.4's "100 rps" to a WAF window limit: 100 rps over a 60-second
# evaluation window ≈ 6000 requests/IP/minute. WAF blocks a source IP once it
# exceeds this count, returning a 429 custom response.

resource "aws_wafv2_web_acl" "this" {
  name  = "${var.name_prefix}-waf"
  scope = "REGIONAL"

  default_action {
    allow {}
  }

  # Custom 429 response body returned when the rate limit blocks a request.
  custom_response_body {
    key          = "rate_limited"
    content      = jsonencode({ error_code = "RATE_LIMITED", message = "Too Many Requests" })
    content_type = "APPLICATION_JSON"
  }

  rule {
    name     = "rate-limit-per-ip"
    priority = 1

    action {
      block {
        custom_response {
          response_code            = 429
          custom_response_body_key = "rate_limited"
        }
      }
    }

    statement {
      rate_based_statement {
        # 100 rps * 60s window = 6000 requests per IP per minute (see note above).
        limit                 = 6000
        aggregate_key_type    = "IP"
        evaluation_window_sec = 60
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.name_prefix}-rate-limit"
      sampled_requests_enabled   = true
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "${var.name_prefix}-waf"
    sampled_requests_enabled   = true
  }

  tags = var.tags
}

# Associate the REGIONAL web ACL with the HTTP API stage (Req 6.4).
resource "aws_wafv2_web_acl_association" "this" {
  resource_arn = aws_apigatewayv2_stage.default.arn
  web_acl_arn  = aws_wafv2_web_acl.this.arn
}
