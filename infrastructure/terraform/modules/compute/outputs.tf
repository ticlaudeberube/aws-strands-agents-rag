# Compute child module outputs (task 15.1).

output "chat_function_arn" {
  description = "ARN of the chat handler Lambda function."
  value       = aws_lambda_function.chat.arn
}

output "chat_function_name" {
  description = "Name of the chat handler Lambda function."
  value       = aws_lambda_function.chat.function_name
}

output "indexing_function_arn" {
  description = "ARN of the indexing handler Lambda function."
  value       = aws_lambda_function.indexing.arn
}

output "indexing_function_name" {
  description = "Name of the indexing handler Lambda function."
  value       = aws_lambda_function.indexing.function_name
}

output "lambda_role_arn" {
  description = "ARN of the shared Lambda execution IAM role."
  value       = aws_iam_role.lambda_exec.arn
}

output "tavily_secret_arn" {
  description = "ARN of the Tavily API key secret."
  value       = aws_secretsmanager_secret.tavily.arn
}

output "redis_secret_arn" {
  description = "ARN of the Redis credentials secret."
  value       = aws_secretsmanager_secret.redis.arn
}

output "chat_function_invoke_arn" {
  description = "Invoke ARN of the chat handler Lambda function (used by API Gateway AWS_PROXY integration)."
  value       = aws_lambda_function.chat.invoke_arn
}
