# Observability child module outputs (task 18.1).

output "errors_total_alarm_arn" {
  description = "ARN of the errors/total CloudWatch metric alarm (Req 12.3)."
  value       = aws_cloudwatch_metric_alarm.errors_total.arn
}

output "errors_total_alarm_name" {
  description = "Name of the errors/total CloudWatch metric alarm."
  value       = aws_cloudwatch_metric_alarm.errors_total.alarm_name
}

output "metric_namespace" {
  description = "CloudWatch metric namespace the alarm watches (StrandsRAG/<stage>), matching the Lambda MetricsEmitter."
  value       = local.metric_namespace
}

output "chat_log_group_name" {
  description = "Name of the chat Lambda CloudWatch log group."
  value       = aws_cloudwatch_log_group.chat.name
}

output "indexing_log_group_name" {
  description = "Name of the indexing Lambda CloudWatch log group."
  value       = aws_cloudwatch_log_group.indexing.name
}

output "log_group_names" {
  description = "Both Lambda log group names (chat + indexing)."
  value = [
    aws_cloudwatch_log_group.chat.name,
    aws_cloudwatch_log_group.indexing.name,
  ]
}

output "alarm_sns_topic_arn" {
  description = "ARN of the optional alarm-notification SNS topic (null when enable_alarm_sns_topic = false)."
  value       = var.enable_alarm_sns_topic ? aws_sns_topic.alarms[0].arn : null
}
