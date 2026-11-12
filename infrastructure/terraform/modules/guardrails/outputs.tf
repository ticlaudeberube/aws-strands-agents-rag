output "guardrail_id" {
  description = "The ID of the Amazon Bedrock Guardrail"
  value       = aws_bedrock_guardrail.rag_guardrail.guardrail_id
}

output "guardrail_arn" {
  description = "The ARN of the Amazon Bedrock Guardrail"
  value       = aws_bedrock_guardrail.rag_guardrail.guardrail_arn
}

output "guardrail_version" {
  description = "The pinned version number of the Amazon Bedrock Guardrail"
  value       = aws_bedrock_guardrail_version.rag_guardrail_v1.version
}
