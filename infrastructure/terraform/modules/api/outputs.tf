# API child module outputs (task 16.1).

output "api_endpoint" {
  description = "Base invoke URL of the HTTP API ($default stage). POST /chat and GET /health are served from here."
  value       = aws_apigatewayv2_stage.default.invoke_url
}

output "api_id" {
  description = "ID of the HTTP API."
  value       = aws_apigatewayv2_api.this.id
}

output "user_pool_id" {
  description = "ID of the Cognito user pool backing the JWT authorizer."
  value       = aws_cognito_user_pool.this.id
}

output "user_pool_client_id" {
  description = "ID of the Cognito user pool app client (JWT audience)."
  value       = aws_cognito_user_pool_client.this.id
}

output "user_pool_endpoint" {
  description = "Cognito user pool endpoint (JWT issuer host)."
  value       = aws_cognito_user_pool.this.endpoint
}

output "web_acl_arn" {
  description = "ARN of the WAFv2 web ACL associated with the API stage."
  value       = aws_wafv2_web_acl.this.arn
}
